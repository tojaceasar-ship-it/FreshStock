import base64
import hashlib
import hmac
import ipaddress
import json
import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    configured = os.getenv("INTEGRATION_ENCRYPTION_KEY")
    if configured:
        try:
            return Fernet(configured.encode())
        except ValueError as exc:
            raise RuntimeError("INTEGRATION_ENCRYPTION_KEY must be a valid Fernet key") from exc
    if settings.ENVIRONMENT == "production" and settings.SECRET_KEY.startswith("super-secret"):
        raise RuntimeError("A production encryption key is required")
    derived = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(derived)


def encrypt_credentials(credentials: Dict[str, Any]) -> str:
    payload = json.dumps(credentials, separators=(",", ":"), sort_keys=True).encode()
    return _fernet().encrypt(payload).decode()


def decrypt_credentials(value: str | None) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        return json.loads(_fernet().decrypt(value.encode()).decode())
    except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Integration credentials cannot be decrypted") from exc


def sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify_webhook_signature(secret: str, timestamp: str, body: bytes, signature: str, tolerance_seconds: int = 300) -> bool:
    try:
        sent = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return False
    if abs((datetime.now(timezone.utc) - sent).total_seconds()) > tolerance_seconds:
        return False
    expected = sign_webhook(secret, timestamp, body)
    supplied = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, supplied)


def _forbidden_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def validate_public_https_url_shape(value: str) -> str:
    """Static validation of an integration base URL, without DNS.

    Rejects anything that must never be persisted as an integration target:
    non-HTTPS schemes, non-443 ports, embedded credentials, literal private,
    loopback, link-local, multicast, reserved and cloud-metadata addresses.

    This deliberately does not resolve the hostname. An integration is
    configured before the remote system may exist, and a DNS lookup at write
    time would reject legitimate configuration for a host that is simply not
    published yet. The request-time check in `validate_public_https_url` still
    resolves the host and re-checks every address before any call is made, which
    is where DNS rebinding must be caught.
    """
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only credential-free HTTPS base URLs are allowed")
    if parsed.port not in (None, 443):
        raise ValueError("Only HTTPS port 443 is allowed")
    host = parsed.hostname.lower().rstrip(".")
    allowed = {item.strip().lower() for item in os.getenv("INTEGRATION_ALLOWED_HOSTS", "").split(",") if item.strip()}
    if allowed and host not in allowed:
        raise ValueError("Host is not on INTEGRATION_ALLOWED_HOSTS")
    # A literal address can be classified immediately; a name is checked at
    # request time once it resolves.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return value.rstrip("/")
    if _forbidden_ip(ip):
        raise ValueError("Private or reserved network targets are forbidden")
    return value.rstrip("/")


def validate_public_https_url(value: str) -> str:
    """Full validation, including DNS resolution. Run before every request."""
    base = validate_public_https_url_shape(value)
    host = urlparse(value).hostname.lower().rstrip(".")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("Host cannot be resolved") from exc
    for address in addresses:
        if _forbidden_ip(ipaddress.ip_address(address)):
            raise ValueError("Private or reserved network targets are forbidden")
    return base
