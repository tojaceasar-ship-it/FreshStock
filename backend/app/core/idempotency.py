"""Idempotency-Key and double-submit protection for mutating endpoints.

Two cooperating guards run before any route handler:

1. Explicit idempotency - a client sends `Idempotency-Key: <key>`. The first
   request is executed and its response stored for 24 h. A replay with the same
   key and identical payload returns the stored response with
   `X-Idempotent-Replay: true`. A replay with a different payload is rejected
   with 409 IDEMPOTENCY_KEY_REUSED.

2. Double-submit guard - a POST/PATCH/PUT/DELETE without an explicit key whose
   payload fingerprint repeats for the same user within
   `DOUBLE_SUBMIT_GUARD_WINDOW` seconds is rejected with 409
   DOUBLE_SUBMIT_DETECTED. This stops accidental double-clicks and network
   retries that fire two identical writes before the first response arrives.

Both guards are keyed on the signed JWT claims (sub, tenant_id), so they work
without an extra database round-trip for identity resolution.
"""

import hashlib
import re
import time
from datetime import datetime, timedelta, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models.idempotency import IdempotencyRecord

KEY_FORMAT_RE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
RECORD_TTL_HOURS = 24
# Requests larger than 1 MB are never stored; the guard still validates the
# fingerprint but falls back to pass-through for the response body.
MAX_STORED_BODY = 1024 * 1024


def _fingerprint(method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.encode())
    digest.update(b"\x00")
    digest.update(path.encode())
    digest.update(b"\x00")
    digest.update(body)
    return digest.hexdigest()


def _key_hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, double_submit_window: float = 2.0):
        super().__init__(app)
        self.double_submit_window = double_submit_window

    async def dispatch(self, request, call_next):
        if request.method not in MUTATING_METHODS:
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        payload = self._authenticated_identity(request)
        if payload is None:
            return await call_next(request)

        body = await request.body()
        # Query parameters can select a different mutation on the same route.
        # Excluding them made rapid PO status transitions collide as duplicates.
        request_target = request.url.path
        if request.url.query:
            request_target += f"?{request.url.query}"
        fingerprint = _fingerprint(request.method, request_target, body)
        raw_key = request.headers.get("idempotency-key", "").strip()

        if raw_key:
            if not KEY_FORMAT_RE.fullmatch(raw_key):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Nieprawidłowy format Idempotency-Key (8-128 znaków: A-Z a-z 0-9 . _ -)"},
                )
            return await self._handle_explicit_key(request, call_next, payload, raw_key, fingerprint, body)

        if self.double_submit_window > 0:
            return await self._handle_double_submit(request, call_next, payload, fingerprint, body)
        return await call_next(request)

    @staticmethod
    def _authenticated_identity(request):
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not token:
            return None
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        try:
            return {"user_id": int(payload["sub"]), "tenant_id": int(payload["tenant_id"])}
        except (KeyError, TypeError, ValueError):
            return None

    async def _handle_explicit_key(self, request, call_next, identity, raw_key, fingerprint, body):
        key_hash = _key_hash(raw_key)
        now = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            existing = (
                db.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.tenant_id == identity["tenant_id"],
                    IdempotencyRecord.key_hash == key_hash,
                    IdempotencyRecord.expires_at > now,
                )
                .first()
            )
            if existing:
                if existing.request_fingerprint != fingerprint:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "detail": "Idempotency-Key użyty wcześniej z innym żądaniem",
                            "error": "IDEMPOTENCY_KEY_REUSED",
                        },
                        headers={"X-Request-ID": request.state.request_id},
                    )
                return Response(
                    content=existing.response_body,
                    status_code=existing.response_status,
                    media_type="application/json",
                    headers={
                        "X-Idempotent-Replay": "true",
                        "X-Request-ID": request.state.request_id,
                    },
                )

            response = await call_next(request)
            if response.status_code >= 500:
                return response

            chunks = b""
            async for chunk in response.body_iterator:
                chunks += chunk
            if len(chunks) > MAX_STORED_BODY:
                headers = dict(response.headers)
                headers.pop("content-length", None)
                return Response(content=chunks, status_code=response.status_code, headers=headers, media_type=response.media_type)

            record = IdempotencyRecord(
                tenant_id=identity["tenant_id"],
                user_id=identity["user_id"],
                key_hash=key_hash,
                request_fingerprint=fingerprint,
                method=request.method,
                path=request.url.path,
                response_status=response.status_code,
                response_body=chunks.decode("utf-8", errors="replace"),
                expires_at=now + timedelta(hours=RECORD_TTL_HOURS),
            )
            db.add(record)
            self._purge_expired(db, identity["tenant_id"], now)
            db.commit()

            headers = dict(response.headers)
            headers.pop("content-length", None)
            headers["X-Idempotent-Replay"] = "false"
            headers["X-Request-ID"] = request.state.request_id
            return Response(content=chunks, status_code=response.status_code, headers=headers, media_type=response.media_type)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def _handle_double_submit(self, request, call_next, identity, fingerprint, body):
        window = self.double_submit_window
        now = time.time()
        db = SessionLocal()
        try:
            recent = (
                db.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.tenant_id == identity["tenant_id"],
                    IdempotencyRecord.user_id == identity["user_id"],
                    IdempotencyRecord.request_fingerprint == fingerprint,
                    IdempotencyRecord.method == request.method,
                    IdempotencyRecord.path == request.url.path,
                )
                .order_by(IdempotencyRecord.created_at.desc())
                .first()
            )
            if recent and recent.created_at:
                created = recent.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - created).total_seconds()
                if age <= window:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "detail": "Wykryto podwójne wysłanie tego samego żądania",
                            "error": "DOUBLE_SUBMIT_DETECTED",
                            "retry_after_seconds": round(window - age, 1),
                        },
                        headers={"X-Request-ID": request.state.request_id},
                    )

            response = await call_next(request)
            # A rejected validation/state transition has made no mutation and
            # must remain retryable after the caller fixes the prerequisite.
            # Recording 4xx responses caused a corrected task completion to be
            # rejected as a duplicate of its earlier failed attempt.
            if response.status_code >= 400 or len(body) > MAX_STORED_BODY:
                return response

            chunks = b""
            async for chunk in response.body_iterator:
                chunks += chunk
            record = IdempotencyRecord(
                tenant_id=identity["tenant_id"],
                user_id=identity["user_id"],
                key_hash=_key_hash(f"auto:{fingerprint}"),
                request_fingerprint=fingerprint,
                method=request.method,
                path=request.url.path,
                response_status=response.status_code,
                response_body=chunks.decode("utf-8", errors="replace"),
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=max(window, 1) * 4),
            )
            db.add(record)
            db.commit()

            headers = dict(response.headers)
            headers.pop("content-length", None)
            headers["X-Request-ID"] = request.state.request_id
            return Response(content=chunks, status_code=response.status_code, headers=headers, media_type=response.media_type)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _purge_expired(db, tenant_id, now):
        db.query(IdempotencyRecord).filter(
            IdempotencyRecord.tenant_id == tenant_id,
            IdempotencyRecord.expires_at <= now,
        ).delete(synchronize_session=False)
