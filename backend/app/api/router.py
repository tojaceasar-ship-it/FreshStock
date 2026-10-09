from fastapi import APIRouter
from app.api.routes import (
    auth, users, categories, suppliers, products, locations,
    batches, stock, deliveries, purchase_orders, sales,
    waste, promotions, inventory_counts, alerts, dashboard,
    reports, ai, stock_movements, audit_logs, traceability, onboarding, scanner_stats, tasks, today, savings, subscription
)
from app.integrations.router import router as integrations_router, bridge_router

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(categories.router, prefix="/categories", tags=["Categories"])
api_router.include_router(suppliers.router, prefix="/suppliers", tags=["Suppliers"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(locations.router, prefix="/locations", tags=["Locations"])
api_router.include_router(batches.router, prefix="/batches", tags=["Batches"])
api_router.include_router(stock.router, prefix="/stock", tags=["Stock"])
api_router.include_router(stock_movements.router, prefix="/stock-movements", tags=["Stock Movements"])
api_router.include_router(deliveries.router, prefix="/deliveries", tags=["Deliveries"])
api_router.include_router(purchase_orders.router, prefix="/purchase-orders", tags=["Purchase Orders"])
api_router.include_router(sales.router, prefix="/sales", tags=["Sales"])
api_router.include_router(waste.router, prefix="/waste", tags=["Waste"])
api_router.include_router(promotions.router, prefix="/promotions", tags=["Promotions"])
api_router.include_router(inventory_counts.router, prefix="/inventory-counts", tags=["Inventory"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI"])
api_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["Audit Log"])
api_router.include_router(traceability.router, prefix="/traceability", tags=["Traceability"])
api_router.include_router(integrations_router, prefix="/integrations", tags=["POS Integrations"])
api_router.include_router(bridge_router, prefix="/bridge", tags=["FreshStock Bridge"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["Store Setup"])
api_router.include_router(scanner_stats.router, prefix="/scanner", tags=["Scanner"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["Task Management"])
api_router.include_router(today.router, prefix="/today", tags=["FreshStock Today"])
api_router.include_router(savings.router, prefix="/savings", tags=["Savings Dashboard"])
api_router.include_router(subscription.router, prefix="/subscription", tags=["Subscription"])
api_router.add_api_route("/me/capabilities", subscription.capabilities, methods=["GET"], tags=["Subscription"])
api_router.add_api_route("/features", subscription.capabilities, methods=["GET"], tags=["Subscription"])
