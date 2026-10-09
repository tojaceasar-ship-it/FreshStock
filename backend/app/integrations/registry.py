from typing import Dict, Type

from app.integrations.base import POSAdapter
from app.integrations.adapters import GenericCSVAdapter, GenericRESTAdapter, LightspeedAdapter, LocalBridgeAdapter, SquareAdapter


class AdapterRegistry:
    _adapters: Dict[str, Type[POSAdapter]] = {}

    @classmethod
    def register(cls, adapter: Type[POSAdapter]) -> None:
        cls._adapters[adapter.provider] = adapter

    @classmethod
    def create(cls, provider: str, credentials: dict | None = None, settings: dict | None = None) -> POSAdapter:
        adapter = cls._adapters.get(provider)
        if not adapter:
            raise ValueError(f"Unsupported POS provider: {provider}")
        return adapter(credentials, settings)

    @classmethod
    def capabilities(cls, provider: str) -> dict:
        adapter = cls._adapters.get(provider)
        return adapter.capabilities.copy() if adapter else {}

    @classmethod
    def providers(cls) -> list[str]:
        return sorted(cls._adapters)


for adapter in (GenericCSVAdapter, GenericRESTAdapter, SquareAdapter, LightspeedAdapter, LocalBridgeAdapter):
    AdapterRegistry.register(adapter)
