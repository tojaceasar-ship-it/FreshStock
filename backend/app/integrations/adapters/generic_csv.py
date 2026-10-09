import csv
import io
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from app.integrations.base import POSAdapter
from app.integrations.schemas import CSVColumnMapping, EventType, NormalizedEvent, NormalizedItem


class GenericCSVAdapter(POSAdapter):
    provider = "generic_csv"
    capabilities = {"sales_read": True, "refunds_read": True, "products_read": False, "inventory_read": False, "inventory_write": False, "prices_write": False, "webhooks": False}

    async def test_connection(self) -> dict:
        return {"ok": True, "provider": self.provider}

    @staticmethod
    def parse(content: bytes, mapping: CSVColumnMapping, delimiter: str = ",", date_format: Optional[str] = None) -> tuple[List[NormalizedEvent], List[dict]]:
        if delimiter not in {",", ";", "\t", "|"}:
            raise ValueError("Unsupported CSV delimiter")
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("CSV file exceeds 10 MB")
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV header is missing")
        required = {mapping.transaction_id, mapping.quantity, mapping.unit_price}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")

        grouped: Dict[str, list] = defaultdict(list)
        errors: List[dict] = []
        for row_number, row in enumerate(reader, 2):
            try:
                tx_id = str(row.get(mapping.transaction_id, "")).strip()
                quantity = Decimal(str(row.get(mapping.quantity, "")).replace(",", "."))
                price = Decimal(str(row.get(mapping.unit_price, "")).replace(",", "."))
                if not tx_id or quantity <= 0 or price < 0:
                    raise ValueError("transaction_id, positive quantity and unit price are required")
                external_id = (str(row.get(mapping.external_product_id, "")).strip() if mapping.external_product_id else "")
                ean = str(row.get(mapping.ean, "")).strip() if mapping.ean else None
                sku = str(row.get(mapping.sku, "")).strip() if mapping.sku else None
                external_id = external_id or ean or sku or ""
                if not external_id:
                    raise ValueError("EAN, SKU or external_product_id is required")
                date_value = str(row.get(mapping.date, "")).strip() if mapping.date else ""
                time_value = str(row.get(mapping.time, "")).strip() if mapping.time else ""
                if date_value:
                    effective_format = date_format or "%Y-%m-%d"
                    if time_value and not any(token in effective_format for token in ("%H", "%I", "%M", "%S")):
                        effective_format = f"{effective_format} %H:%M:%S"
                    timestamp = datetime.strptime(f"{date_value} {time_value}".strip(), effective_format)
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                else:
                    timestamp = datetime.now(timezone.utc)
                total_raw = row.get(mapping.total) if mapping.total else None
                total = Decimal(str(total_raw).replace(",", ".")) if total_raw not in (None, "") else quantity * price
                grouped[tx_id].append((row, NormalizedItem(
                    external_product_id=external_id, ean=ean or None, sku=sku or None,
                    name=(str(row.get(mapping.name, "")).strip() if mapping.name else None),
                    quantity=quantity, unit_price=price, total=total,
                ), timestamp))
            except (ValueError, InvalidOperation) as exc:
                errors.append({"row": row_number, "error": str(exc)})

        events = []
        for tx_id, rows in grouped.items():
            first_row, _, timestamp = rows[0]
            events.append(NormalizedEvent(
                event_type=EventType.SALE, provider="generic_csv",
                external_event_id=f"csv:{tx_id}", external_transaction_id=tx_id,
                location_external_id=(str(first_row.get(mapping.location, "")).strip() if mapping.location else None),
                timestamp=timestamp, currency="PLN", items=[item for _, item, _ in rows],
            ))
        return events, errors
