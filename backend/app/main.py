from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.router import api_router
from app.core.rate_limit import RateLimitMiddleware
from app.core.database import engine, get_db
from app.core.observability import RequestContextMiddleware
from app.core.idempotency import IdempotencyMiddleware
from app.core.monitoring import MonitoringMiddleware, database_health_snapshot, metrics
from app.core.deps import require_permission
from sqlalchemy import text

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="FreshStock - System zarządzania sklepem spożywczym",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.add_middleware(
    RateLimitMiddleware,
    default_limit=settings.RATE_LIMIT_DEFAULT,
    auth_limit=settings.RATE_LIMIT_AUTH,
)
# Middleware order: last added runs first (outermost).
# Monitoring -> CORS -> RequestContext -> Idempotency -> RateLimit -> route.
app.add_middleware(
    IdempotencyMiddleware,
    double_submit_window=settings.DOUBLE_SUBMIT_GUARD_WINDOW,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    expose_headers=["X-Request-ID", "Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-Idempotent-Replay", "X-Total-Count"],
)
app.add_middleware(MonitoringMiddleware)

app.include_router(api_router, prefix="/api")

@app.get("/")
def root():
    return {"message": "FreshStock API", "version": settings.VERSION, "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok", "version": settings.VERSION}


@app.get("/ready")
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "error"})


@app.get("/api/monitoring/metrics")
def monitoring_metrics(db=Depends(get_db), current_user=Depends(require_permission("dashboard:read"))):
    """Operational snapshot for the paid-pilot readiness gate."""
    return {"process": metrics.snapshot(), "database": database_health_snapshot(db)}
