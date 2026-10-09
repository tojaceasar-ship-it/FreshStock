import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

from app.integrations.schemas import EventType, NormalizedEvent, NormalizedItem


def normalize_generic_event(payload: Dict[str, Any], provider: str) -> NormalizedEvent:
    items = []
    for raw in payload.get("items") or []:
        quantity = Decimal(str(raw.get("quantity", 0)))
        unit_price = Decimal(str(raw.get("unit_price", 0)))
        items.append(NormalizedItem(
            external_product_id=str(raw.get("external_product_id") or raw.get("ean") or raw.get("sku") or ""),
            ean=str(raw["ean"]).strip() if raw.get("ean") else None,
            sku=str(raw["sku"]).strip() if raw.get("sku") else None,
            name=raw.get("name"),
            quantity=quantity,
            unit_price=unit_price,
            total=Decimal(str(raw.get("total", quantity * unit_price))),
        ))
    timestamp = payload.get("timestamp") or datetime.now(timezone.utc)
    return NormalizedEvent(
        event_type=EventType(str(payload.get("event_type", "SALE")).upper()),
        provider=provider,
        external_event_id=str(payload.get("external_event_id") or payload.get("id") or ""),
        external_transaction_id=str(payload.get("external_transaction_id") or payload.get("transaction_id") or ""),
        location_external_id=payload.get("location_external_id"),
        timestamp=timestamp,
        currency=str(payload.get("currency", "PLN")),
        items=items,
        raw=payload,
    )


def payload_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
