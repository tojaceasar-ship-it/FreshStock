from datetime import datetime
from typing import List, Optional

import httpx

from app.integrations.base import POSAdapter
from app.integrations.security import validate_public_https_url


class GenericRESTAdapter(POSAdapter):
    provider = "generic_rest"
    capabilities = {"sales_read": True, "refunds_read": True, "products_read": True, "inventory_read": False, "inventory_write": False, "prices_write": False, "webhooks": True}

    def _base_url(self) -> str:
        return validate_public_https_url(str(self.settings.get("base_url", "")))

    def _headers(self) -> dict:
        auth_type = self.settings.get("auth_type", "bearer")
        token = self.credentials.get("token") or self.credentials.get("api_key")
        if not token:
            return {}
        if auth_type == "api_key":
            return {str(self.settings.get("api_key_header", "X-API-Key")): str(token)}
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {token}"}
        raise ValueError("Unsupported authentication type")

    def _endpoint(self, key: str) -> str:
        value = str(self.settings.get(key, "")).strip()
        if not value.startswith("/") or value.startswith("//") or "?" in value or "#" in value:
            raise ValueError(f"{key} must be a fixed relative path")
        return value

    async def _get(self, endpoint_key: str, params: Optional[dict] = None) -> list:
        url = self._base_url() + self._endpoint(endpoint_key)
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=False) as client:
            response = await client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            data = response.json()
        if isinstance(data, list):
            items = data
        elif isinstance(data.get("data"), list):
            items = data["data"]
        else:
            items = None

        if items is not None:
            if endpoint_key in {"sales_endpoint", "refunds_endpoint"}:
                default_type = "REFUND" if endpoint_key == "refunds_endpoint" else "SALE"
                return [item if item.get("event_type") and item.get("external_event_id") else self._normalize_state_sale(item, default_type) for item in items]
            return items

        # Some POS simulators expose one state document instead of separate
        # collections. Keep this compatibility path explicit and read-only.
        if endpoint_key == "products_endpoint" and isinstance(data.get("products"), list):
            return data["products"]
        if endpoint_key == "sales_endpoint" and isinstance(data.get("sales"), list):
            sales = [self._normalize_state_sale(item, "SALE") for item in data["sales"]]
            refunds = [self._normalize_state_sale(item, "REFUND") for item in data.get("refunds", [])]
            return sales + refunds
        return []

    @staticmethod
    def _normalize_state_sale(payload: dict, default_event_type: str) -> dict:
        # A sale remains a SALE even when its current state is VOIDED/REFUNDED.
        # The separate refunds feed carries the compensating REFUND/VOID event.
        kind = str(payload.get("kind", "")).upper()
        event_type = "VOID" if default_event_type == "REFUND" and kind == "VOID" else default_event_type
        event_id = str(payload.get("external_event_id") or payload.get("id") or "")
        transaction_id = str(
            payload.get("external_transaction_id")
            or payload.get("transaction_id")
            or payload.get("original_sale_id")
            or payload.get("sale_id")
            or event_id
        )
        items = []
        for item in payload.get("items") or []:
            quantity = item.get("quantity", item.get("qty", 0))
            unit_price = item.get("unit_price", item.get("price", 0))
            items.append({
                "external_product_id": str(item.get("external_product_id") or item.get("product_id") or item.get("ean") or item.get("sku") or ""),
                "ean": item.get("ean"),
                "sku": item.get("sku"),
                "name": item.get("name"),
                "quantity": quantity,
                "unit_price": unit_price,
                "total": item.get("total", float(quantity) * float(unit_price)),
            })
        return {
            "event_type": event_type,
            "external_event_id": event_id,
            "external_transaction_id": transaction_id,
            "timestamp": payload.get("timestamp") or payload.get("created_at") or datetime.now().isoformat(),
            "currency": payload.get("currency", "EUR"),
            "items": items,
        }

    async def test_connection(self) -> dict:
        await self._get("products_endpoint")
        return {"ok": True, "provider": self.provider}

    async def get_products(self) -> List[dict]:
        return await self._get("products_endpoint")

    async def get_sales(self, since: Optional[datetime] = None) -> List[dict]:
        return await self._get("sales_endpoint", {"since": since.isoformat()} if since else None)

    async def get_sales_page(self, since: Optional[datetime], *, offset: int, limit: int) -> List[dict]:
        params = {"offset": offset, "limit": limit}
        if since:
            params["since"] = since.isoformat()
        return await self._get("sales_endpoint", params)

    async def get_refunds(self, since: Optional[datetime] = None) -> List[dict]:
        if not self.settings.get("refunds_endpoint"):
            return []
        return await self._get("refunds_endpoint", {"since": since.isoformat()} if since else None)

    async def parse_webhook(self, request) -> dict:
        return await request.json()
