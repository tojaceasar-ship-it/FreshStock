from abc import ABC, abstractmethod


class BillingProvider(ABC):
    """Provider-neutral billing boundary. Entitlements never depend on Stripe internals."""

    @abstractmethod
    def create_checkout(self, tenant_id: int, plan: str): ...

    @abstractmethod
    def create_subscription(self, tenant_id: int, plan: str): ...

    @abstractmethod
    def change_plan(self, tenant_id: int, plan: str): ...

    @abstractmethod
    def cancel_subscription(self, tenant_id: int): ...

    @abstractmethod
    def handle_webhook(self, payload: bytes, signature: str): ...


class ManualBillingProvider(BillingProvider):
    """Current provider: plan activation is handled internally until payments are connected."""
    def create_checkout(self, tenant_id: int, plan: str): return {"mode": "manual", "tenant_id": tenant_id, "plan": plan}
    def create_subscription(self, tenant_id: int, plan: str): return self.create_checkout(tenant_id, plan)
    def change_plan(self, tenant_id: int, plan: str): return self.create_checkout(tenant_id, plan)
    def cancel_subscription(self, tenant_id: int): return {"mode": "manual", "tenant_id": tenant_id, "cancelled": True}
    def handle_webhook(self, payload: bytes, signature: str): raise NotImplementedError("No external billing provider configured")
