from app.integrations.base import POSAdapter


class LocalBridgeAdapter(POSAdapter):
    provider = "local_bridge"
    capabilities = {"sales_read": True, "refunds_read": True, "products_read": True, "inventory_read": True, "inventory_write": False, "prices_write": False, "webhooks": False}

    async def test_connection(self) -> dict:
        return {"ok": True, "provider": self.provider, "mode": "push"}
