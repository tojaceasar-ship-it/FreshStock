import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import ValidationError
import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_permission, require_roles
from app.integrations.adapters.generic_csv import GenericCSVAdapter
from app.integrations.models import (
    CSVMappingTemplate, IntegrationError, IntegrationEvent, IntegrationSyncLog,
    PendingReturn, POSBridge, POSIntegration, POSProductMapping,
)
from app.integrations.normalizer import normalize_generic_event
from app.integrations.registry import AdapterRegistry
from app.integrations.schemas import (
    BridgeHeartbeatRequest, BridgeRegisterRequest, CSVColumnMapping,
    IntegrationCreate, IntegrationUpdate, MappingCreate, MappingUpdate,
    ResolveReturnRequest,
)
from app.integrations.security import (
    decrypt_credentials, encrypt_credentials, validate_public_https_url_shape,
    verify_webhook_signature,
)
from app.integrations.service import (
    get_integration, ingest_event, map_product, resolve_return, sync_integration,
    tenant_id_for,
)
from app.models.product import Product
from app.models.batch import Batch
from app.models.location import WarehouseLocation
from app.models.sale import Sale
from app.models.user import UserRole
from app.services.audit import add_audit_log

router = APIRouter()
bridge_router = APIRouter()
logger = logging.getLogger(__name__)

VALID_STATUSES = {"ACTIVE", "DISABLED", "ERROR", "AUTH_REQUIRED"}
VALID_SYNC_MODES = {"WEBHOOK", "POLLING", "HYBRID", "CSV", "BRIDGE"}


def _integration_payload(db: Session, integration: POSIntegration) -> dict:
    mapped = db.query(func.count(POSProductMapping.id)).filter(
        POSProductMapping.tenant_id == integration.tenant_id,
        POSProductMapping.integration_id == integration.id,
    ).scalar() or 0
    unresolved = db.query(func.count(IntegrationError.id)).filter(
        IntegrationError.tenant_id == integration.tenant_id,
        IntegrationError.integration_id == integration.id,
        IntegrationError.resolved == False,
    ).scalar() or 0
    unmapped = db.query(func.count(IntegrationError.id)).filter(
        IntegrationError.tenant_id == integration.tenant_id,
        IntegrationError.integration_id == integration.id,
        IntegrationError.error_type == "UNMAPPED_PRODUCT",
        IntegrationError.resolved == False,
    ).scalar() or 0
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sales_today = db.query(
        func.count(IntegrationEvent.id), func.coalesce(func.sum(Sale.total_amount), 0),
    ).join(Sale, Sale.id == IntegrationEvent.sale_id).filter(
        IntegrationEvent.tenant_id == integration.tenant_id,
        IntegrationEvent.integration_id == integration.id,
        IntegrationEvent.event_type == "SALE",
        IntegrationEvent.status == "PROCESSED",
        Sale.sale_date >= today,
    ).first()
    bridge = db.query(POSBridge).filter(
        POSBridge.tenant_id == integration.tenant_id,
        POSBridge.integration_id == integration.id,
        POSBridge.status == "ACTIVE",
    ).order_by(POSBridge.last_seen.desc().nulls_last()).first()
    now = datetime.now(timezone.utc)
    last_success = integration.last_success_at
    if last_success and last_success.tzinfo is None:
        last_success = last_success.replace(tzinfo=timezone.utc)
    bridge_seen = bridge.last_seen if bridge else None
    if bridge_seen and bridge_seen.tzinfo is None:
        bridge_seen = bridge_seen.replace(tzinfo=timezone.utc)
    stale_hours = round((now - last_success).total_seconds() / 3600, 1) if last_success else None
    if integration.status == "DISABLED":
        health, health_reason = "DISABLED", "Integracja jest wyłączona"
    elif integration.status in {"ERROR", "AUTH_REQUIRED"}:
        health, health_reason = "ERROR", "Integracja wymaga naprawy połączenia lub autoryzacji"
    elif integration.sync_mode == "BRIDGE" and (not bridge_seen or (now - bridge_seen).total_seconds() > 900):
        health, health_reason = "ERROR", "Bridge nie zgłosił się w ciągu ostatnich 15 minut"
    elif unresolved:
        health, health_reason = "WARNING", f"Nierozwiązane błędy: {int(unresolved)}"
    elif integration.sync_mode in {"POLLING", "HYBRID", "WEBHOOK"} and (stale_hours is None or stale_hours > 24):
        health, health_reason = "WARNING", "Brak udanej synchronizacji w ciągu ostatnich 24 godzin"
    else:
        health, health_reason = "OK", "Integracja działa prawidłowo"
    return {
        "id": integration.id, "tenant_id": integration.tenant_id,
        "provider": integration.provider, "name": integration.name,
        "status": integration.status, "sync_mode": integration.sync_mode,
        "external_merchant_id": integration.external_merchant_id,
        "external_location_id": integration.external_location_id,
        "last_sync_at": integration.last_sync_at, "last_success_at": integration.last_success_at,
        "last_error_at": integration.last_error_at, "created_at": integration.created_at,
        "capabilities": AdapterRegistry.capabilities(integration.provider),
        "mapped_products": int(mapped), "unmapped_products": int(unmapped), "error_count": int(unresolved),
        "sales_today_count": int(sales_today[0] or 0), "sales_today_amount": float(sales_today[1] or 0),
        "health": health, "health_reason": health_reason, "hours_since_success": stale_hours,
        "bridge_last_seen": bridge_seen, "bridge_version": bridge.version if bridge else None,
    }


admin_dependency = require_roles(UserRole.OWNER, UserRole.MANAGER)


def _validate_settings_base_url(settings_dict: Optional[dict]) -> None:
    """Reject an unsafe integration base URL at configuration time.

    Uses the static shape check, so a host that is not published yet can still
    be configured, while non-HTTPS, non-443, credential-bearing and literal
    private/loopback/metadata targets are refused before they are stored. The
    adapter performs the full DNS-resolving check again before every request.
    """
    if not settings_dict:
        return
    base_url = str(settings_dict.get("base_url") or "").strip()
    if not base_url:
        return
    try:
        validate_public_https_url_shape(base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Niebezpieczny adres integracji: {exc}") from exc


@router.get("/providers")
def providers(current_user=Depends(require_permission("integrations:read"))):
    return [{"provider": provider, "capabilities": AdapterRegistry.capabilities(provider)} for provider in AdapterRegistry.providers()]


@router.post("/csv/preview")
async def csv_preview(
    integration_id: int = Form(...),
    mapping: str = Form(...),
    delimiter: str = Form(","),
    date_format: Optional[str] = Form(None),
    template_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    tenant_id = tenant_id_for(current_user)
    integration = get_integration(db, integration_id, tenant_id)
    if integration.provider != "generic_csv":
        raise HTTPException(status_code=400, detail="Wybrana integracja nie jest typu Generic CSV")
    if template_id:
        template = db.query(CSVMappingTemplate).filter(CSVMappingTemplate.id == template_id, CSVMappingTemplate.tenant_id == tenant_id, CSVMappingTemplate.integration_id == integration_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Szablon nie istnieje")
        column_mapping = CSVColumnMapping.model_validate(template.column_mapping)
        delimiter, date_format = template.delimiter, template.date_format
    else:
        try:
            column_mapping = CSVColumnMapping.model_validate_json(mapping)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="Nieprawidłowe mapowanie kolumn") from exc
    events, invalid_rows = GenericCSVAdapter.parse(await file.read(), column_mapping, delimiter, date_format)
    matched = unmapped = duplicate = 0
    preview_rows = []
    for event in events:
        is_duplicate = db.query(IntegrationEvent.id).filter(IntegrationEvent.integration_id == integration.id, IntegrationEvent.external_event_id == event.external_event_id).first() is not None
        if is_duplicate:
            duplicate += len(event.items)
        for item in event.items:
            product, method = map_product(db, integration, external_product_id=item.external_product_id, ean=item.ean, sku=item.sku)
            if product:
                matched += 1
            else:
                unmapped += 1
            if len(preview_rows) < 100:
                preview_rows.append({
                    "transaction_id": event.external_transaction_id, "external_product_id": item.external_product_id,
                    "ean": item.ean, "sku": item.sku, "name": item.name, "quantity": str(item.quantity),
                    "unit_price": str(item.unit_price), "status": "DUPLICATE" if is_duplicate else ("MATCHED" if product else "UNMAPPED"),
                    "freshstock_product_id": product.id if product else None, "freshstock_product_name": product.name if product else None,
                    "mapping_method": method,
                })
    db.rollback()  # preview must never persist automatically discovered mappings
    return {
        "records": sum(len(event.items) for event in events) + len(invalid_rows),
        "transactions": len(events), "matched": matched, "unmapped": unmapped,
        "invalid": len(invalid_rows), "duplicate": duplicate,
        "invalid_rows": invalid_rows[:100], "preview": preview_rows,
    }


@router.post("/csv/import")
async def csv_import(
    integration_id: int = Form(...), mapping: str = Form(...), delimiter: str = Form(","),
    date_format: Optional[str] = Form(None), template_name: Optional[str] = Form(None),
    template_id: Optional[int] = Form(None), file: UploadFile = File(...),
    db: Session = Depends(get_db), current_user=Depends(admin_dependency),
):
    tenant_id = tenant_id_for(current_user)
    integration = get_integration(db, integration_id, tenant_id)
    if integration.provider != "generic_csv":
        raise HTTPException(status_code=400, detail="Wybrana integracja nie jest typu Generic CSV")
    if template_id:
        template = db.query(CSVMappingTemplate).filter(CSVMappingTemplate.id == template_id, CSVMappingTemplate.tenant_id == tenant_id, CSVMappingTemplate.integration_id == integration_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Szablon nie istnieje")
        column_mapping = CSVColumnMapping.model_validate(template.column_mapping)
        delimiter, date_format = template.delimiter, template.date_format
    else:
        try:
            column_mapping = CSVColumnMapping.model_validate_json(mapping)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="Nieprawidłowe mapowanie kolumn") from exc
    events, invalid_rows = GenericCSVAdapter.parse(await file.read(), column_mapping, delimiter, date_format)
    sync_log = IntegrationSyncLog(tenant_id=tenant_id, integration_id=integration.id, sync_type="CSV_IMPORT", records_received=len(events), records_failed=len(invalid_rows), status="RUNNING")
    db.add(sync_log)
    if template_name and not template_id:
        existing_template = db.query(CSVMappingTemplate).filter(CSVMappingTemplate.integration_id == integration.id, CSVMappingTemplate.name == template_name).first()
        if existing_template:
            existing_template.column_mapping, existing_template.delimiter, existing_template.date_format = column_mapping.model_dump(), delimiter, date_format
        else:
            db.add(CSVMappingTemplate(tenant_id=tenant_id, integration_id=integration.id, name=template_name, delimiter=delimiter, date_format=date_format, column_mapping=column_mapping.model_dump()))
    db.flush()
    results = []
    for event in events:
        result = ingest_event(db, integration, event, user_id=current_user.id)
        results.append(result)
        if result.get("duplicate") or result.get("status") in {"PROCESSED", "IGNORED"}:
            sync_log.records_processed += 1
        else:
            sync_log.records_failed += 1
    sync_log.finished_at = datetime.now(timezone.utc)
    sync_log.status = "SUCCESS" if not sync_log.records_failed else "PARTIAL"
    integration.last_sync_at = sync_log.finished_at
    if sync_log.records_processed:
        integration.last_success_at = sync_log.finished_at
    add_audit_log(db, user_id=current_user.id, action="CSV_IMPORT", entity_type="pos_integration", entity_id=integration.id, new_values={"records": len(events), "processed": sync_log.records_processed, "failed": sync_log.records_failed}, details=f"Import CSV: {file.filename}")
    db.commit()
    return {"received": len(events), "processed": sync_log.records_processed, "failed": sync_log.records_failed, "invalid_rows": invalid_rows[:100], "results": results}


@router.get("/csv/templates")
def csv_templates(integration_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("integrations:read"))):
    tenant_id = tenant_id_for(current_user)
    get_integration(db, integration_id, tenant_id)
    return db.query(CSVMappingTemplate).filter(CSVMappingTemplate.tenant_id == tenant_id, CSVMappingTemplate.integration_id == integration_id).order_by(CSVMappingTemplate.name).all()


@router.get("/poll")
async def scheduled_poll(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    cron_secret = os.getenv("CRON_SECRET", "")
    supplied = (authorization or "").removeprefix("Bearer ")
    if not cron_secret or not hmac.compare_digest(cron_secret, supplied):
        raise HTTPException(status_code=401, detail="Nieprawidłowy sekret harmonogramu")
    integrations = db.query(POSIntegration).filter(
        POSIntegration.status == "ACTIVE",
        POSIntegration.sync_mode.in_(["POLLING", "HYBRID"]),
        POSIntegration.provider.notin_(["generic_csv", "local_bridge"]),
    ).all()
    results = []
    for integration in integrations:
        try:
            result = await sync_integration(db, integration, user_id=None)
            results.append({"integration_id": integration.id, "status": "SUCCESS", **result})
        except HTTPException as exc:
            results.append({"integration_id": integration.id, "status": "FAILED", "detail": exc.detail})
    return {"integrations": len(integrations), "results": results}


@router.get("")
def list_integrations(db: Session = Depends(get_db), current_user=Depends(require_permission("integrations:read"))):
    tenant_id = tenant_id_for(current_user)
    integrations = db.query(POSIntegration).filter(POSIntegration.tenant_id == tenant_id).order_by(POSIntegration.created_at.desc()).all()
    return [_integration_payload(db, item) for item in integrations]


@router.get("/pos/{provider}/{integration_id}/catalog/{ean}")
def pos_catalog_product(
    provider: str,
    integration_id: int,
    ean: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Return one active warehouse product for an authenticated POS terminal."""
    integration = db.query(POSIntegration).filter(
        POSIntegration.id == integration_id,
        POSIntegration.provider == provider,
        POSIntegration.status == "ACTIVE",
    ).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integracja nie istnieje")
    credentials = decrypt_credentials(integration.credentials_encrypted)
    expected = str(credentials.get("token") or "")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Nieprawidłowy token POS")
    ean = ean.strip()
    if not ean or len(ean) > 50:
        raise HTTPException(status_code=422, detail="Nieprawidłowy EAN")
    product = db.query(Product).filter(
        Product.tenant_id == integration.tenant_id,
        Product.ean == ean,
        Product.is_active == True,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produktu o tym EAN nie ma w magazynie")
    rows = db.query(
        Batch.warehouse_location_id,
        func.coalesce(func.sum(Batch.quantity_available), 0),
    ).filter(
        Batch.tenant_id == integration.tenant_id,
        Batch.product_id == product.id,
        Batch.quantity_available > 0,
    ).group_by(Batch.warehouse_location_id).all()
    location_ids = [row[0] for row in rows if row[0] is not None]
    locations = {
        item.id: item.code for item in db.query(WarehouseLocation).filter(
            WarehouseLocation.tenant_id == integration.tenant_id,
            WarehouseLocation.id.in_(location_ids),
        ).all()
    } if location_ids else {}
    available = sum(int(row[1] or 0) for row in rows)
    return {
        "id": str(product.id), "ean": product.ean, "sku": product.sku,
        "name": product.name, "price": float(product.selling_price or 0),
        "vat": float(product.vat_rate or 0), "available_quantity": available,
        "locations": [
            {"id": row[0], "code": locations.get(row[0]), "quantity": row[1] or Decimal("0")}
            for row in rows
        ],
    }


@router.post("")
def create_integration(payload: IntegrationCreate, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    from app.services.plans import PlanService
    tenant_id = tenant_id_for(current_user)
    feature = {"generic_csv": "generic_csv_pos", "generic_rest": "generic_rest", "local_bridge": "freshstock_bridge"}.get(payload.provider, "realtime_pos")
    if not PlanService.has_feature(db, tenant_id, feature):
        from app.services.plans import FEATURE_MIN_PLAN
        raise HTTPException(status_code=403, detail={"error": "FEATURE_NOT_AVAILABLE", "feature": feature, "required_plan": FEATURE_MIN_PLAN.get(feature, "ENTERPRISE")})
    if payload.provider != "generic_csv" and not PlanService.has_feature(db, tenant_id, "multiple_pos_integrations"):
        PlanService.assert_limit(db, tenant_id, "pos_integrations")
    if payload.provider not in AdapterRegistry.providers():
        raise HTTPException(status_code=400, detail="Nieobsługiwany provider")
    if payload.sync_mode not in VALID_SYNC_MODES:
        raise HTTPException(status_code=400, detail="Nieprawidłowy tryb synchronizacji")
    # Validate the configured base URL now, not on first sync. The adapter also
    # revalidates before every request, but a dangerous target must never be
    # persisted in the first place.
    _validate_settings_base_url(payload.settings)
    has_credentials = bool(payload.credentials)
    integration = POSIntegration(
        tenant_id=tenant_id_for(current_user), provider=payload.provider, name=payload.name,
        status="ACTIVE" if payload.provider in {"generic_csv", "local_bridge"} or has_credentials else "AUTH_REQUIRED",
        sync_mode=payload.sync_mode, external_merchant_id=payload.external_merchant_id,
        external_location_id=payload.external_location_id,
        credentials_encrypted=encrypt_credentials(payload.credentials) if payload.credentials else None,
        settings=payload.settings,
    )
    db.add(integration)
    db.flush()
    add_audit_log(db, user_id=current_user.id, action="INTEGRATION_CREATED", entity_type="pos_integration", entity_id=integration.id, new_values={"provider": integration.provider, "name": integration.name, "sync_mode": integration.sync_mode})
    db.commit()
    db.refresh(integration)
    return _integration_payload(db, integration)


@router.get("/{integration_id}")
def integration_detail(integration_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("integrations:read"))):
    return _integration_payload(db, get_integration(db, integration_id, tenant_id_for(current_user)))


@router.patch("/{integration_id}")
def update_integration(integration_id: int, payload: IntegrationUpdate, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    integration = get_integration(db, integration_id, tenant_id_for(current_user))
    data = payload.model_dump(exclude_unset=True)
    credentials = data.pop("credentials", None)
    if data.get("status") and data["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Nieprawidłowy status")
    if data.get("sync_mode") and data["sync_mode"] not in VALID_SYNC_MODES:
        raise HTTPException(status_code=400, detail="Nieprawidłowy tryb synchronizacji")
    if "settings" in data:
        _validate_settings_base_url(data["settings"])
    old = {key: getattr(integration, key) for key in data}
    for key, value in data.items():
        setattr(integration, key, value)
    if credentials is not None:
        integration.credentials_encrypted = encrypt_credentials(credentials)
    add_audit_log(db, user_id=current_user.id, action="INTEGRATION_CONNECTED" if credentials else "INTEGRATION_UPDATED", entity_type="pos_integration", entity_id=integration.id, old_values=old, new_values=data)
    db.commit()
    return _integration_payload(db, integration)


@router.delete("/{integration_id}")
def disable_integration(integration_id: int, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    integration = get_integration(db, integration_id, tenant_id_for(current_user))
    integration.status = "DISABLED"
    integration.credentials_encrypted = None
    add_audit_log(db, user_id=current_user.id, action="INTEGRATION_DISABLED", entity_type="pos_integration", entity_id=integration.id)
    db.commit()
    return {"message": "Integracja została wyłączona, a credentials usunięte"}


@router.post("/{integration_id}/test")
async def test_integration(integration_id: int, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    integration = get_integration(db, integration_id, tenant_id_for(current_user))
    adapter = AdapterRegistry.create(integration.provider, decrypt_credentials(integration.credentials_encrypted), integration.settings or {})
    try:
        result = await adapter.test_connection()
        integration.status = "ACTIVE" if result.get("ok") else "AUTH_REQUIRED"
        if result.get("ok"):
            integration.last_success_at = datetime.now(timezone.utc)
        else:
            integration.last_error_at = datetime.now(timezone.utc)
        db.commit()
        return result
    except httpx.HTTPStatusError as exc:
        integration.status = "ERROR"
        integration.last_error_at = datetime.now(timezone.utc)
        db.commit()
        status_code = exc.response.status_code
        logger.warning("Generic REST connection test returned HTTP %s for integration %s", status_code, integration.id)
        raise HTTPException(status_code=502, detail=f"POS API zwróciło HTTP {status_code}") from exc
    except (ValueError, RuntimeError) as exc:
        integration.status = "ERROR"
        integration.last_error_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning("Generic REST configuration error for integration %s: %s", integration.id, exc)
        raise HTTPException(status_code=502, detail=f"Błąd konfiguracji Generic REST: {exc}") from exc
    except Exception as exc:
        integration.status = "ERROR"
        integration.last_error_at = datetime.now(timezone.utc)
        db.commit()
        logger.exception("Generic REST connection test failed for integration %s", integration.id)
        raise HTTPException(status_code=502, detail="Test połączenia nie powiódł się z powodu błędu sieci") from exc


@router.post("/{integration_id}/sync")
async def manual_sync(integration_id: int, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    integration = get_integration(db, integration_id, tenant_id_for(current_user), lock=True)
    add_audit_log(db, user_id=current_user.id, action="MANUAL_SYNC", entity_type="pos_integration", entity_id=integration.id)
    db.flush()
    return await sync_integration(db, integration, user_id=current_user.id)


@router.get("/{integration_id}/mappings")
def mappings(integration_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("integrations:read"))):
    tenant_id = tenant_id_for(current_user)
    get_integration(db, integration_id, tenant_id)
    rows = db.query(POSProductMapping).filter(POSProductMapping.tenant_id == tenant_id, POSProductMapping.integration_id == integration_id).order_by(POSProductMapping.updated_at.desc()).all()
    return [{"id": row.id, "external_product_id": row.external_product_id, "freshstock_product_id": row.freshstock_product_id, "freshstock_product_name": row.product.name if row.product else None, "ean": row.ean, "sku": row.sku, "mapping_method": row.mapping_method, "confidence": float(row.confidence)} for row in rows]


@router.post("/{integration_id}/mappings")
def create_mapping(integration_id: int, payload: MappingCreate, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    tenant_id = tenant_id_for(current_user)
    integration = get_integration(db, integration_id, tenant_id)
    product = db.query(Product).filter(Product.id == payload.freshstock_product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produkt FreshStock nie istnieje")
    existing = db.query(POSProductMapping).filter(POSProductMapping.integration_id == integration.id, POSProductMapping.external_product_id == payload.external_product_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Mapowanie tego produktu już istnieje")
    row = POSProductMapping(tenant_id=tenant_id, integration_id=integration.id, provider=integration.provider, external_product_id=payload.external_product_id, freshstock_product_id=product.id, ean=payload.ean, sku=payload.sku, mapping_method="MANUAL", confidence=1)
    db.add(row); db.flush()
    add_audit_log(db, user_id=current_user.id, action="PRODUCT_MAPPING_CREATED", entity_type="pos_product_mapping", entity_id=row.id, new_values={"external_product_id": row.external_product_id, "freshstock_product_id": row.freshstock_product_id})
    db.commit()
    return {"id": row.id, "message": "Mapowanie utworzone"}


@router.patch("/{integration_id}/mappings/{mapping_id}")
def update_mapping(integration_id: int, mapping_id: int, payload: MappingUpdate, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    tenant_id = tenant_id_for(current_user)
    get_integration(db, integration_id, tenant_id)
    row = db.query(POSProductMapping).filter(POSProductMapping.id == mapping_id, POSProductMapping.integration_id == integration_id, POSProductMapping.tenant_id == tenant_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Mapowanie nie istnieje")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Brak danych do aktualizacji")

    old_values = {key: getattr(row, key) for key in data}
    if "freshstock_product_id" in data:
        product = db.query(Product).filter(
            Product.id == data["freshstock_product_id"],
            Product.tenant_id == tenant_id,
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail="Produkt FreshStock nie istnieje")
        data["freshstock_product_id"] = product.id
        data["mapping_method"] = "MANUAL"
        data["confidence"] = 1

    for key, value in data.items():
        setattr(row, key, value)
    add_audit_log(
        db, user_id=current_user.id, action="PRODUCT_MAPPING_CHANGED",
        entity_type="pos_product_mapping", entity_id=row.id,
        old_values=old_values, new_values=data,
    )
    db.commit()
    return {"message": "Mapowanie zmienione", "id": row.id}


@router.get("/{integration_id}/errors")
def errors(integration_id: int, resolved: Optional[bool] = None, db: Session = Depends(get_db), current_user=Depends(require_permission("integrations:read"))):
    tenant_id = tenant_id_for(current_user); get_integration(db, integration_id, tenant_id)
    query = db.query(IntegrationError).filter(IntegrationError.tenant_id == tenant_id, IntegrationError.integration_id == integration_id)
    if resolved is not None: query = query.filter(IntegrationError.resolved == resolved)
    return query.order_by(IntegrationError.created_at.desc()).limit(500).all()


@router.get("/{integration_id}/returns")
def pending_returns(integration_id: int, status: Optional[str] = None, db: Session = Depends(get_db), current_user=Depends(require_permission("integrations:read"))):
    tenant_id = tenant_id_for(current_user)
    get_integration(db, integration_id, tenant_id)
    query = db.query(PendingReturn).filter(
        PendingReturn.tenant_id == tenant_id,
        PendingReturn.integration_id == integration_id,
    )
    if status:
        query = query.filter(PendingReturn.status == status)
    return query.order_by(PendingReturn.created_at.desc()).limit(200).all()


@router.post("/{integration_id}/returns/{return_id}/resolve")
def resolve_pending_return(integration_id: int, return_id: int, payload: ResolveReturnRequest, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    tenant_id = tenant_id_for(current_user); get_integration(db, integration_id, tenant_id)
    pending = db.query(PendingReturn).filter(PendingReturn.id == return_id, PendingReturn.integration_id == integration_id, PendingReturn.tenant_id == tenant_id).first()
    if not pending: raise HTTPException(status_code=404, detail="Zwrot nie istnieje")
    result = resolve_return(db, pending, action=payload.action, batch_id=payload.batch_id, user_id=current_user.id)
    db.commit(); return result


@router.post("/{integration_id}/errors/{error_id}/resolve")
def resolve_error(integration_id: int, error_id: int, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    tenant_id = tenant_id_for(current_user); get_integration(db, integration_id, tenant_id)
    error = db.query(IntegrationError).filter(IntegrationError.id == error_id, IntegrationError.integration_id == integration_id, IntegrationError.tenant_id == tenant_id).first()
    if not error: raise HTTPException(status_code=404, detail="Błąd nie istnieje")
    error.resolved = True; error.resolved_by = current_user.id; error.resolved_at = datetime.now(timezone.utc)
    add_audit_log(db, user_id=current_user.id, action="INTEGRATION_ERROR_RESOLVED", entity_type="integration_error", entity_id=error.id)
    db.commit(); return {"message": "Błąd oznaczono jako rozwiązany"}


@router.get("/{integration_id}/logs")
def logs(integration_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("integrations:read"))):
    tenant_id = tenant_id_for(current_user); get_integration(db, integration_id, tenant_id)
    return db.query(IntegrationSyncLog).filter(IntegrationSyncLog.tenant_id == tenant_id, IntegrationSyncLog.integration_id == integration_id).order_by(IntegrationSyncLog.started_at.desc()).limit(200).all()


@router.post("/{provider}/{integration_id}/webhook")
async def webhook(provider: str, integration_id: int, request: Request, db: Session = Depends(get_db), x_pos_timestamp: str = Header(...), x_pos_signature: str = Header(...)):
    integration = db.query(POSIntegration).filter(POSIntegration.id == integration_id, POSIntegration.provider == provider, POSIntegration.status == "ACTIVE").first()
    if not integration: raise HTTPException(status_code=404, detail="Integracja nie istnieje")
    body = await request.body()
    if len(body) > 1024 * 1024: raise HTTPException(status_code=413, detail="Webhook payload too large")
    credentials = decrypt_credentials(integration.credentials_encrypted)
    # Generic REST terminals may use their integration token as the signing
    # secret, avoiding a second credential while retaining HMAC protection.
    secret = credentials.get("webhook_secret") or credentials.get("token")
    if not secret or not verify_webhook_signature(str(secret), x_pos_timestamp, body, x_pos_signature):
        raise HTTPException(status_code=401, detail="Nieprawidłowy lub przeterminowany podpis webhooka")
    try:
        payload = json.loads(body)
        event = normalize_generic_event(payload, provider)
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Nieprawidłowy payload webhooka") from exc
    result = ingest_event(db, integration, event, durable_receipt=True)
    db.commit()
    return {"ok": True, **result}


def _bridge_auth(db: Session, bridge_id: str, secret: str) -> POSBridge:
    bridge = db.query(POSBridge).filter(POSBridge.bridge_id == bridge_id, POSBridge.status == "ACTIVE").first()
    if not bridge or not hmac.compare_digest(str(decrypt_credentials(bridge.secret_encrypted).get("secret", "")), secret):
        raise HTTPException(status_code=401, detail="Nieprawidłowe dane Bridge")
    return bridge


@bridge_router.post("/register")
def register_bridge(payload: BridgeRegisterRequest, db: Session = Depends(get_db), current_user=Depends(admin_dependency)):
    tenant_id = tenant_id_for(current_user); integration = get_integration(db, payload.integration_id, tenant_id)
    if integration.provider != "local_bridge": raise HTTPException(status_code=400, detail="Integracja nie jest typu Local Bridge")
    bridge_secret = secrets.token_urlsafe(32); bridge_id = "br_" + secrets.token_hex(12)
    bridge = POSBridge(tenant_id=tenant_id, integration_id=integration.id, bridge_id=bridge_id, store_id=payload.store_id, secret_encrypted=encrypt_credentials({"secret": bridge_secret}), version=payload.version)
    db.add(bridge); db.commit()
    return {"bridge_id": bridge_id, "secret": bridge_secret, "message": "Sekret jest wyświetlany tylko raz"}


@bridge_router.post("/events")
async def bridge_events(
    request: Request,
    db: Session = Depends(get_db),
    x_bridge_id: str = Header(...),
    x_bridge_timestamp: str = Header(...),
    x_bridge_signature: str = Header(...),
):
    bridge = db.query(POSBridge).filter(POSBridge.bridge_id == x_bridge_id, POSBridge.status == "ACTIVE").first()
    if not bridge:
        raise HTTPException(status_code=401, detail="Nieprawidłowe dane Bridge")
    body = await request.body()
    secret = str(decrypt_credentials(bridge.secret_encrypted).get("secret", ""))
    if not secret or not verify_webhook_signature(secret, x_bridge_timestamp, body, x_bridge_signature):
        raise HTTPException(status_code=401, detail="Nieprawidłowy lub przeterminowany podpis Bridge")
    integration = db.query(POSIntegration).filter(POSIntegration.id == bridge.integration_id, POSIntegration.tenant_id == bridge.tenant_id).first()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Nieprawidłowy JSON") from exc
    raw_events = payload if isinstance(payload, list) else [payload]
    results = []
    for raw in raw_events:
        results.append(ingest_event(db, integration, normalize_generic_event(raw, "local_bridge"), durable_receipt=True))
    bridge.last_seen = datetime.now(timezone.utc); db.commit()
    return {"accepted": len(results), "results": results}


@bridge_router.post("/heartbeat")
def bridge_heartbeat(payload: BridgeHeartbeatRequest, db: Session = Depends(get_db), x_bridge_id: str = Header(...), x_bridge_secret: str = Header(...)):
    bridge = _bridge_auth(db, x_bridge_id, x_bridge_secret); bridge.last_seen = datetime.now(timezone.utc)
    if payload.version: bridge.version = payload.version
    db.commit(); return {"status": "ok", "server_time": datetime.now(timezone.utc)}


@bridge_router.get("/config")
def bridge_config(db: Session = Depends(get_db), x_bridge_id: str = Header(...), x_bridge_secret: str = Header(...)):
    bridge = _bridge_auth(db, x_bridge_id, x_bridge_secret)
    integration = db.query(POSIntegration).filter(POSIntegration.id == bridge.integration_id, POSIntegration.tenant_id == bridge.tenant_id).first()
    return {"bridge_id": bridge.bridge_id, "store_id": bridge.store_id, "integration_id": integration.id, "provider": integration.provider, "sync_mode": integration.sync_mode}
