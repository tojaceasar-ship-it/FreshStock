import logging
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.models import (
    IntegrationError, IntegrationEvent, IntegrationSyncLog, PendingReturn,
    POSIntegration, POSProductMapping,
)
from app.integrations.normalizer import normalize_generic_event, payload_hash
from app.integrations.registry import AdapterRegistry
from app.integrations.schemas import EventType, NormalizedEvent
from app.integrations.security import decrypt_credentials
from app.models.batch import Batch
from app.models.product import Product
from app.models.sale import Sale, SaleSource
from app.models.stock import Stock
from app.models.stock_movement import MovementType, StockMovement
from app.models.waste import Waste, WasteReason
from app.services.audit import add_audit_log
from app.services.sales_engine import SalesEngineItem, SalesEngineError, process_sale, reverse_sale

logger = logging.getLogger("freshstock.integrations")


def tenant_id_for(user) -> int:
    return int(getattr(user, "tenant_id", 1))


def get_integration(db: Session, integration_id: int, tenant_id: int, *, lock: bool = False) -> POSIntegration:
    query = db.query(POSIntegration).filter(POSIntegration.id == integration_id, POSIntegration.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    integration = query.first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integracja nie istnieje")
    return integration


def map_product(db: Session, integration: POSIntegration, *, external_product_id: str, ean: Optional[str], sku: Optional[str]) -> tuple[Optional[Product], Optional[str]]:
    cache = db.info.setdefault("pos_product_cache", {})
    cache_key = (integration.id, external_product_id)
    if cache_key in cache:
        return cache[cache_key]
    mapping = db.query(POSProductMapping).filter(
        POSProductMapping.tenant_id == integration.tenant_id,
        POSProductMapping.integration_id == integration.id,
        POSProductMapping.external_product_id == external_product_id,
    ).first()
    if mapping:
        result = (mapping.product, mapping.mapping_method)
        cache[cache_key] = result
        return result

    product = None
    method = None
    if ean:
        product = db.query(Product).filter(Product.ean == ean).first()
        method = "EAN" if product else None
    if not product and sku:
        product = db.query(Product).filter(Product.sku == sku).first()
        method = "SKU" if product else None
    if not product:
        return None, None

    mapping = POSProductMapping(
        tenant_id=integration.tenant_id, integration_id=integration.id, provider=integration.provider,
        external_product_id=external_product_id, freshstock_product_id=product.id,
        ean=ean, sku=sku, mapping_method=method, confidence=Decimal("1"),
    )
    db.add(mapping)
    db.flush()
    result = (product, method)
    cache[cache_key] = result
    return result


def _record_error(db: Session, integration: POSIntegration, event: Optional[IntegrationEvent], error_type: str, message: str, payload: Optional[dict] = None) -> IntegrationError:
    error = IntegrationError(
        tenant_id=integration.tenant_id, integration_id=integration.id,
        event_id=event.id if event else None, error_type=error_type,
        message=message[:2000], payload=payload,
    )
    db.add(error)
    return error


def _structured_log(integration: POSIntegration, event: NormalizedEvent, action: str, status: str) -> None:
    logger.info("integration_event", extra={
        "integration_id": integration.id, "provider": integration.provider,
        "external_event_id": event.external_event_id, "tenant_id": integration.tenant_id,
        "action": action, "status": status,
    })


def ingest_event(
    db: Session,
    integration: POSIntegration,
    event: NormalizedEvent,
    *,
    user_id: Optional[int] = None,
    durable_receipt: bool = False,
) -> dict:
    db.info["tenant_id"] = integration.tenant_id
    existing = db.query(IntegrationEvent).filter(
        IntegrationEvent.integration_id == integration.id,
        IntegrationEvent.external_event_id == event.external_event_id,
    ).first()
    if existing and existing.status != "FAILED":
        _structured_log(integration, event, "duplicate", "IGNORED")
        return {"duplicate": True, "event_id": existing.id, "status": existing.status, "sale_id": existing.sale_id}

    event_payload = event.model_dump(mode="json", exclude={"raw"})
    if existing:
        record = existing
        db.query(IntegrationError).filter(
            IntegrationError.event_id == record.id,
            IntegrationError.resolved == False,
        ).delete(synchronize_session=False)
        record.payload_hash = payload_hash(event_payload)
        record.payload = event_payload
        record.status = "PROCESSING"
        record.error_message = None
        record.processed_at = None
    else:
        record = IntegrationEvent(
            tenant_id=integration.tenant_id, integration_id=integration.id, provider=integration.provider,
            external_event_id=event.external_event_id, external_transaction_id=event.external_transaction_id,
            event_type=event.event_type.value, payload_hash=payload_hash(event_payload), payload=event_payload,
            status="PROCESSING",
        )
        db.add(record)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            duplicate = db.query(IntegrationEvent).filter(
                IntegrationEvent.integration_id == integration.id,
                IntegrationEvent.external_event_id == event.external_event_id,
            ).first()
            return {"duplicate": True, "event_id": duplicate.id if duplicate else None, "status": duplicate.status if duplicate else "IGNORED"}

    if durable_receipt:
        record.status = "RECEIVED"
        db.commit()
        record.status = "PROCESSING"

    try:
        if event.event_type == EventType.SALE:
            prior_transaction = db.query(IntegrationEvent).filter(
                IntegrationEvent.integration_id == integration.id,
                IntegrationEvent.external_transaction_id == event.external_transaction_id,
                IntegrationEvent.event_type == EventType.SALE.value,
                IntegrationEvent.sale_id.isnot(None),
            ).order_by(IntegrationEvent.id.desc()).first()
            if prior_transaction:
                record.status = "IGNORED"
                record.sale_id = prior_transaction.sale_id
                record.processed_at = datetime.now(timezone.utc)
                record.error_message = "Duplicate external transaction"
                _structured_log(integration, event, "duplicate_transaction", "IGNORED")
                return {"duplicate": True, "event_id": record.id, "status": record.status, "sale_id": record.sale_id}

            engine_items = []
            unmapped = []
            for item in event.items:
                if item.quantity != item.quantity.to_integral_value():
                    _record_error(db, integration, record, "INVALID_QUANTITY", "FreshStock currently requires whole-unit POS quantities", {"external_product_id": item.external_product_id, "quantity": str(item.quantity)})
                    unmapped.append(item.external_product_id)
                    continue
                product, _ = map_product(db, integration, external_product_id=item.external_product_id, ean=item.ean, sku=item.sku)
                if not product:
                    _record_error(db, integration, record, "UNMAPPED_PRODUCT", f"Brak mapowania produktu {item.external_product_id}", item.model_dump(mode="json"))
                    unmapped.append(item.external_product_id)
                    continue
                engine_items.append(SalesEngineItem(product_id=product.id, quantity=Decimal(item.quantity), unit_price=item.unit_price))
            if unmapped:
                record.status = "FAILED"
                record.error_message = f"Unmapped or invalid products: {', '.join(unmapped)}"
                record.processed_at = datetime.now(timezone.utc)
                _structured_log(integration, event, "sale", "FAILED")
                return {"duplicate": False, "event_id": record.id, "status": record.status, "errors": unmapped}

            sale, shortages = process_sale(
                db, sale_number=f"POS-{integration.id}-{event.external_transaction_id}",
                sale_date=event.timestamp, source=SaleSource.POS, user_id=user_id,
                items=engine_items, allow_partial_stock=True, reference_type="pos_sale",
            )
            for shortage in shortages:
                _record_error(db, integration, record, "INVENTORY_DESYNC", "POS quantity exceeds available FreshStock batches", shortage)
            record.sale_id = sale.id
            record.status = "PROCESSED"
            add_audit_log(db, user_id=user_id, action="POS_SALE", entity_type="integration_event", entity_id=record.id, new_values={"sale_id": sale.id, "shortages": shortages}, details=f"Przetworzono sprzedaż POS {event.external_transaction_id}")

        elif event.event_type == EventType.REFUND:
            original = db.query(IntegrationEvent).filter(
                IntegrationEvent.integration_id == integration.id,
                IntegrationEvent.external_transaction_id == event.external_transaction_id,
                IntegrationEvent.event_type == EventType.SALE.value,
                IntegrationEvent.sale_id.isnot(None),
            ).order_by(IntegrationEvent.id.desc()).first()
            suggestions = []
            if original and original.sale:
                suggestions = [
                    {"product_id": item.product_id, "batch_id": item.batch_id, "quantity": str(item.quantity)}
                    for item in original.sale.items if item.batch_id
                ]
            requested_items = []
            for item in event.items:
                product, _ = map_product(db, integration, external_product_id=item.external_product_id, ean=item.ean, sku=item.sku)
                item_payload = item.model_dump(mode="json")
                item_payload["freshstock_product_id"] = product.id if product else None
                requested_items.append(item_payload)
            pending = PendingReturn(
                tenant_id=integration.tenant_id, integration_id=integration.id, event_id=record.id,
                original_sale_id=original.sale_id if original else None,
                items={"requested": requested_items, "suggested_batches": suggestions},
            )
            db.add(pending)
            _record_error(db, integration, record, "RETURN_PENDING", "Zwrot wymaga decyzji RETURN_TO_STOCK lub WASTE", pending.items)
            record.status = "PROCESSED"

        elif event.event_type == EventType.VOID:
            original = db.query(IntegrationEvent).filter(
                IntegrationEvent.integration_id == integration.id,
                IntegrationEvent.external_transaction_id == event.external_transaction_id,
                IntegrationEvent.event_type == EventType.SALE.value,
                IntegrationEvent.sale_id.isnot(None),
            ).order_by(IntegrationEvent.id.desc()).first()
            if not original or not original.sale:
                _record_error(db, integration, record, "UNKNOWN_TRANSACTION", "Nie znaleziono sprzedaży do anulowania", {"external_transaction_id": event.external_transaction_id})
                record.status = "FAILED"
                record.error_message = "Original sale not found"
            else:
                reversed_quantity = reverse_sale(db, sale=original.sale, user_id=user_id)
                record.status = "PROCESSED"
                add_audit_log(db, user_id=user_id, action="POS_VOID", entity_type="sale", entity_id=original.sale_id, new_values={"reversed_quantity": reversed_quantity}, details="Odwrócono ruchy oryginalnej sprzedaży")
        else:
            record.status = "IGNORED"
            record.error_message = "Event stored for reconciliation; no inventory mutation configured"

        record.processed_at = datetime.now(timezone.utc)
        integration.last_success_at = datetime.now(timezone.utc)
        _structured_log(integration, event, event.event_type.value.lower(), record.status)
        return {"duplicate": False, "event_id": record.id, "status": record.status, "sale_id": record.sale_id}
    except (SalesEngineError, ValueError) as exc:
        record.status = "FAILED"
        record.error_message = str(exc)[:2000]
        record.processed_at = datetime.now(timezone.utc)
        integration.last_error_at = datetime.now(timezone.utc)
        _record_error(db, integration, record, "PROCESSING_ERROR", "Event processing failed", {"reason": str(exc)})
        _structured_log(integration, event, event.event_type.value.lower(), "FAILED")
        return {"duplicate": False, "event_id": record.id, "status": "FAILED"}


async def sync_integration(db: Session, integration: POSIntegration, *, user_id: Optional[int]) -> dict:
    db.info.pop("pos_product_cache", None)
    db.info.pop("sales_engine_cache", None)
    now = datetime.now(timezone.utc)
    if integration.sync_lock_until and integration.sync_lock_until > now:
        raise HTTPException(status_code=409, detail="Synchronizacja tej integracji już trwa")
    original_expire_on_commit = db.expire_on_commit
    db.expire_on_commit = False
    integration.sync_lock_until = now + timedelta(minutes=2)
    integration.last_sync_at = now
    log = IntegrationSyncLog(tenant_id=integration.tenant_id, integration_id=integration.id, sync_type="MANUAL", status="RUNNING")
    db.add(log)
    db.commit()

    try:
        adapter = AdapterRegistry.create(integration.provider, decrypt_credentials(integration.credentials_encrypted), integration.settings or {})
        runtime_settings = dict(integration.settings or {})
        cursor_offset = int(runtime_settings.get("_sync_offset", 0))
        cursor_since_raw = runtime_settings.get("_sync_since")
        if cursor_since_raw:
            since = datetime.fromisoformat(cursor_since_raw)
        else:
            since = (integration.last_success_at - timedelta(minutes=5)) if integration.last_success_at else None
            runtime_settings["_sync_since"] = since.isoformat() if since else None
        page_size = 10
        if hasattr(adapter, "get_sales_page"):
            sales = await asyncio.wait_for(adapter.get_sales_page(since, offset=cursor_offset, limit=page_size), timeout=20)
        else:
            sales = await asyncio.wait_for(adapter.get_sales(since), timeout=20)
        has_more = hasattr(adapter, "get_sales_page") and len(sales) == page_size
        refunds = []
        if not has_more and adapter.capabilities.get("refunds_read"):
            refunds = await asyncio.wait_for(adapter.get_refunds(since), timeout=20)
        raw_events = sales + refunds
        log.records_received = len(raw_events)
        batch_size = max(10, len(raw_events))
        for index, raw in enumerate(raw_events, start=1):
            try:
                # Validation and domain failures are represented as event results;
                # avoid a SAVEPOINT round-trip for every record. This is critical
                # for remote Postgres (Neon) during large POS imports.
                event = normalize_generic_event(raw, integration.provider)
                result = ingest_event(db, integration, event, user_id=user_id)
                db.flush()
                if result["status"] in {"PROCESSED", "IGNORED"} or result.get("duplicate"):
                    log.records_processed += 1
                else:
                    log.records_failed += 1
                if index % batch_size == 0:
                    db.commit()
            except Exception:
                if not db.is_active:
                    raise
                log.records_failed += 1
        db.commit()
        if has_more:
            runtime_settings["_sync_offset"] = cursor_offset + len(sales)
        else:
            runtime_settings.pop("_sync_offset", None)
            runtime_settings.pop("_sync_since", None)
        integration.settings = runtime_settings
        integration.last_success_at = datetime.now(timezone.utc)
        log.status = "SUCCESS" if not log.records_failed else "PARTIAL"
        return {
            "received": log.records_received, "processed": log.records_processed,
            "failed": log.records_failed, "has_more": has_more,
            "next_offset": runtime_settings.get("_sync_offset"),
        }
    except Exception as exc:
        db.rollback()
        integration = db.query(POSIntegration).filter(POSIntegration.id == integration.id).first()
        log = db.query(IntegrationSyncLog).filter(IntegrationSyncLog.id == log.id).first()
        integration.last_error_at = datetime.now(timezone.utc)
        log.status = "FAILED"
        log.error_message = "POS API synchronization failed"
        logger.exception("integration_sync_failed", extra={"integration_id": integration.id, "tenant_id": integration.tenant_id, "provider": integration.provider})
        raise HTTPException(status_code=502, detail="Synchronizacja z POS nie powiodła się") from exc
    finally:
        db.expire_on_commit = original_expire_on_commit
        db.info.pop("pos_product_cache", None)
        db.info.pop("sales_engine_cache", None)
        integration.sync_lock_until = None
        log.finished_at = datetime.now(timezone.utc)
        db.commit()


def resolve_return(db: Session, pending: PendingReturn, *, action: str, batch_id: Optional[int], user_id: int) -> dict:
    if pending.status != "RETURN_PENDING":
        raise HTTPException(status_code=409, detail="Zwrot został już rozstrzygnięty")
    requested = pending.items.get("requested", [])
    suggestions = pending.items.get("suggested_batches", [])
    if action not in {"RETURN_TO_STOCK", "WASTE"}:
        raise HTTPException(status_code=400, detail="Dozwolone akcje: RETURN_TO_STOCK, WASTE")

    processed = 0
    for item in requested:
        quantity_decimal = Decimal(str(item["quantity"]))
        if quantity_decimal != quantity_decimal.to_integral_value():
            raise HTTPException(status_code=400, detail="Zwrot wymaga całkowitej ilości")
        quantity = quantity_decimal
        selected_batch_id = batch_id
        if not selected_batch_id:
            matching = next((entry for entry in suggestions if entry["product_id"] == item.get("freshstock_product_id")), None)
            selected_batch_id = matching.get("batch_id") if matching else None
        if not selected_batch_id:
            raise HTTPException(status_code=400, detail="Wybierz partię dla zwrotu")
        batch = db.query(Batch).filter(Batch.id == selected_batch_id).with_for_update().first()
        if not batch:
            raise HTTPException(status_code=404, detail="Wybrana partia nie istnieje")
        product_id = item.get("freshstock_product_id")
        if not product_id:
            raise HTTPException(status_code=400, detail="Najpierw zmapuj produkt ze zwrotu")
        if batch.product_id != product_id:
            raise HTTPException(status_code=400, detail="Wybrana partia należy do innego produktu")
        if action == "RETURN_TO_STOCK":
            batch.quantity_available += quantity
            if batch.warehouse_location_id:
                stock = db.query(Stock).filter(Stock.product_id == batch.product_id, Stock.location_id == batch.warehouse_location_id).with_for_update().first()
                if stock:
                    stock.quantity += quantity
            db.add(StockMovement(product_id=batch.product_id, batch_id=batch.id, quantity=quantity, movement_type=MovementType.RETURN, destination_location_id=batch.warehouse_location_id, user_id=user_id, reason="Zwrot POS przyjęty na stan", reference_id=str(pending.id), reference_type="pos_refund"))
        else:
            product = db.query(Product).filter(Product.id == batch.product_id).first()
            db.add(Waste(product_id=batch.product_id, batch_id=batch.id, quantity=quantity, purchase_value=(batch.purchase_price or product.purchase_price) * quantity, sale_value=product.selling_price * quantity, reason=WasteReason.OTHER, notes="Zwrot POS skierowany do strat", reported_by=user_id, location_id=batch.warehouse_location_id))
        processed += quantity
    pending.status = action
    pending.resolved_by = user_id
    pending.resolved_at = datetime.now(timezone.utc)
    error = db.query(IntegrationError).filter(IntegrationError.event_id == pending.event_id, IntegrationError.error_type == "RETURN_PENDING").first()
    if error:
        error.resolved = True
        error.resolved_by = user_id
        error.resolved_at = datetime.now(timezone.utc)
    add_audit_log(db, user_id=user_id, action="REFUND_RESOLVED", entity_type="pending_return", entity_id=pending.id, new_values={"action": action, "quantity": processed, "batch_id": batch_id})
    return {"status": pending.status, "quantity": processed}
