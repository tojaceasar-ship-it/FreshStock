"""Operational monitoring: in-process metrics, structured access log,
CORS rejection detection and a DB-backed health snapshot.

The metrics endpoint answers the paid-pilot readiness questions without
any external monitoring stack:
- API error rate (4xx/5xx counters, latency percentiles)
- CORS preflight rejections (browser-blocked requests are invisible to
  ordinary access logs, so they are counted here explicitly)
- POS integration health, unresolved integration errors
- CSV/import sync outcomes over the last 24 hours
- Write-path activity (sales, deliveries, waste) over the last 24 hours
"""

import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("freshstock.monitoring")

LATENCY_SAMPLES = 1000


class MetricsCollector:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests_total = 0
        self.requests_2xx = 0
        self.requests_4xx = 0
        self.requests_5xx = 0
        self.cors_rejected_preflights = 0
        self.latencies = deque(maxlen=LATENCY_SAMPLES)

    def record(self, status_code: int, duration_ms: float, method: str, path: str, origin: str):
        with self.lock:
            self.requests_total += 1
            if 200 <= status_code < 300:
                self.requests_2xx += 1
            elif 400 <= status_code < 500:
                self.requests_4xx += 1
                if method == "OPTIONS" and origin:
                    self.cors_rejected_preflights += 1
            elif status_code >= 500:
                self.requests_5xx += 1
            self.latencies.append(duration_ms)
        logger.info(
            "access method=%s path=%s status=%s duration_ms=%s origin=%s",
            method, path, status_code, round(duration_ms, 1), origin or "-",
        )

    def snapshot(self) -> dict:
        with self.lock:
            latencies = sorted(self.latencies)
            total = len(latencies)
            avg = sum(latencies) / total if total else 0.0
            p95 = latencies[int(total * 0.95)] if total else 0.0
            p99 = latencies[int(total * 0.99)] if total else 0.0
            return {
                "requests_total": self.requests_total,
                "requests_2xx": self.requests_2xx,
                "requests_4xx": self.requests_4xx,
                "requests_5xx": self.requests_5xx,
                "error_rate_5xx": round(self.requests_5xx / self.requests_total, 5) if self.requests_total else 0.0,
                "cors_rejected_preflights": self.cors_rejected_preflights,
                "latency_avg_ms": round(avg, 1),
                "latency_p95_ms": round(p95, 1),
                "latency_p99_ms": round(p99, 1),
                "latency_samples": total,
            }


metrics = MetricsCollector()


class MonitoringMiddleware(BaseHTTPMiddleware):
    """Outermost middleware: measures every request end-to-end."""

    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        metrics.record(
            response.status_code,
            duration_ms,
            request.method,
            request.url.path,
            request.headers.get("origin", ""),
        )
        return response


def database_health_snapshot(db) -> dict:
    """Operational indicators computed from existing tables."""
    from sqlalchemy import func

    from app.integrations.models import (
        IntegrationError,
        IntegrationSyncLog,
        POSIntegration,
    )
    from app.models.audit_log import AuditLog
    from app.models.delivery import Delivery
    from app.models.sale import Sale
    from app.models.waste import Waste

    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)

    integrations = db.query(POSIntegration).all()
    health_counts = {"OK": 0, "WARNING": 0, "ERROR": 0, "DISABLED": 0}
    for integration in integrations:
        if integration.status == "DISABLED":
            health_counts["DISABLED"] += 1
        elif integration.status in {"ERROR", "AUTH_REQUIRED"}:
            health_counts["ERROR"] += 1
        else:
            last_success = integration.last_success_at
            if last_success and last_success.tzinfo is None:
                last_success = last_success.replace(tzinfo=timezone.utc)
            stale = last_success is None or (now - last_success).total_seconds() > 86400
            unresolved = db.query(func.count(IntegrationError.id)).filter(
                IntegrationError.integration_id == integration.id,
                IntegrationError.resolved == False,  # noqa: E712
            ).scalar() or 0
            health_counts["WARNING" if (stale or unresolved) else "OK"] += 1

    sync_summary = {}
    for row in db.query(
        IntegrationSyncLog.status, func.count(IntegrationSyncLog.id)
    ).filter(IntegrationSyncLog.started_at >= since_24h).group_by(IntegrationSyncLog.status).all():
        sync_summary[row[0]] = row[1]

    unresolved_errors = db.query(func.count(IntegrationError.id)).filter(
        IntegrationError.resolved == False,  # noqa: E712
        IntegrationError.created_at >= since_24h,
    ).scalar() or 0

    sales_24h = db.query(func.count(Sale.id)).filter(Sale.sale_date >= since_24h).scalar() or 0
    deliveries_24h = db.query(func.count(Delivery.id)).filter(Delivery.created_at >= since_24h).scalar() or 0
    waste_24h = db.query(func.count(Waste.id)).filter(Waste.created_at >= since_24h).scalar() or 0
    audit_24h = db.query(func.count(AuditLog.id)).filter(AuditLog.created_at >= since_24h).scalar() or 0

    return {
        "integrations": {
            "total": len(integrations),
            "by_health": health_counts,
        },
        "unresolved_integration_errors_24h": int(unresolved_errors),
        "sync_logs_24h": sync_summary,
        "write_activity_24h": {
            "sales": int(sales_24h),
            "deliveries": int(deliveries_24h),
            "waste": int(waste_24h),
            "audit_events": int(audit_24h),
        },
        "server_time": now.isoformat(),
    }
