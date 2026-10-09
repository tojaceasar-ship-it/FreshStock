from collections import defaultdict, deque
from threading import Lock
from time import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Lightweight per-instance limiter; suitable as a Vercel abuse guard."""

    def __init__(self, app, default_limit: int = 120, auth_limit: int = 15):
        super().__init__(app)
        self.default_limit = default_limit
        self.auth_limit = auth_limit
        self.requests = defaultdict(deque)
        self.lock = Lock()

    async def dispatch(self, request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
        is_auth = request.url.path in {"/api/auth/login", "/api/auth/bootstrap", "/api/auth/register-store"} and request.method == "POST"
        window = 900 if is_auth else 60
        limit = self.auth_limit if is_auth else self.default_limit
        # Normal traffic is isolated per endpoint so loading a dashboard with many
        # parallel widgets cannot exhaust one global bucket.
        key = (client_ip, "auth-login") if is_auth else (client_ip, request.method, request.url.path)
        now = time()

        with self.lock:
            bucket = self.requests[key]
            while bucket and bucket[0] <= now - window:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window - (now - bucket[0])))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Zbyt wiele żądań. Spróbuj ponownie później."},
                    headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"},
                )
            bucket.append(now)
            remaining = max(0, limit - len(bucket))

        response = await call_next(request)
        # Successful authentication must not consume the brute-force budget.
        # Keep only client errors (invalid/malformed credentials) in that bucket.
        if is_auth and (response.status_code < 400 or response.status_code >= 500):
            with self.lock:
                try:
                    self.requests[key].remove(now)
                except ValueError:
                    pass
                remaining = max(0, limit - len(self.requests[key]))
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
