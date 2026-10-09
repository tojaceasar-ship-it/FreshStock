from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional


DEFAULT_CAPABILITIES = {
    "sales_read": False,
    "refunds_read": False,
    "products_read": False,
    "inventory_read": False,
    "inventory_write": False,
    "prices_write": False,
    "webhooks": False,
}


class POSAdapter(ABC):
    provider = "base"
    capabilities: Dict[str, bool] = DEFAULT_CAPABILITIES.copy()

    def __init__(self, credentials: Optional[dict] = None, settings: Optional[dict] = None):
        self.credentials = credentials or {}
        self.settings = settings or {}

    @abstractmethod
    async def test_connection(self) -> dict:
        raise NotImplementedError

    async def get_products(self) -> List[dict]:
        raise NotImplementedError(f"{self.provider} does not support products_read")

    async def get_sales(self, since: Optional[datetime] = None) -> List[dict]:
        raise NotImplementedError(f"{self.provider} does not support sales_read")

    async def get_refunds(self, since: Optional[datetime] = None) -> List[dict]:
        raise NotImplementedError(f"{self.provider} does not support refunds_read")

    async def get_inventory(self) -> List[dict]:
        raise NotImplementedError(f"{self.provider} does not support inventory_read")

    async def push_inventory(self, items: List[dict]) -> dict:
        raise NotImplementedError(f"{self.provider} does not support inventory_write")

    async def push_prices(self, items: List[dict]) -> dict:
        raise NotImplementedError(f"{self.provider} does not support prices_write")

    async def register_webhooks(self) -> dict:
        raise NotImplementedError(f"{self.provider} does not support webhooks")

    async def parse_webhook(self, request: Any) -> dict:
        raise NotImplementedError(f"{self.provider} does not support webhooks")
