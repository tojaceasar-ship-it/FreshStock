from app.integrations.base import POSAdapter


class LightspeedAdapter(POSAdapter):
    provider = "lightspeed"
    capabilities = {"sales_read": True, "refunds_read": True, "products_read": True, "inventory_read": True, "inventory_write": False, "prices_write": False, "webhooks": True}

    async def test_connection(self) -> dict:
        return {"ok": False, "configured": False, "message": "Lightspeed OAuth adapter contract is ready; OAuth credentials are required"}
