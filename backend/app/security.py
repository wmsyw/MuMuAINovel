"""Security helpers for sessions and outbound URL validation."""
import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import time
from typing import Iterable
from urllib.parse import urlparse

from fastapi import HTTPException

from app.config import settings

_EPHEMERAL_SESSION_SECRET = secrets.token_urlsafe(48)
_WORKSHOP_PROXY_SIGNATURE_MAX_AGE_SECONDS = 300


def _session_secret() -> bytes:
    secret = getattr(settings, "SESSION_SECRET_KEY", None) or getattr(settings, "session_secret_key", None)
    if not secret:
        secret = _EPHEMERAL_SESSION_SECRET
    return str(secret).encode("utf-8")


def create_session_token(user_id: str, max_age_seconds: int) -> str:
    payload = {
        "uid": user_id,
        "exp": int(time.time()) + max_age_seconds,
        "nonce": secrets.token_urlsafe(16),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
    signature = hmac.new(_session_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{payload_b64}.{signature_b64}"


def verify_session_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    payload_b64, signature_b64 = token.split(".", 1)
    expected = hmac.new(_session_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    try:
        provided = base64.urlsafe_b64decode(signature_b64 + "=" * (-len(signature_b64) % 4))
    except Exception:
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        payload_raw = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        payload = json.loads(payload_raw.decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    user_id = payload.get("uid")
    return user_id if isinstance(user_id, str) and user_id else None


def _workshop_proxy_secret() -> bytes | None:
    secret = getattr(settings, "WORKSHOP_PROXY_SECRET", None)
    return str(secret).encode("utf-8") if secret else None


def create_workshop_proxy_signature(
    *,
    method: str,
    path: str,
    timestamp: str,
    instance_id: str,
    user_id: str | None,
) -> str | None:
    secret = _workshop_proxy_secret()
    if not secret:
        return None
    payload = "\n".join([method.upper(), path, timestamp, instance_id, user_id or ""])
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_workshop_proxy_signature(
    *,
    method: str,
    path: str,
    timestamp: str | None,
    instance_id: str | None,
    user_id: str | None,
    signature: str | None,
    now: int | None = None,
) -> bool:
    if not timestamp or not instance_id or not signature:
        return False
    secret = _workshop_proxy_secret()
    if not secret:
        return False
    if not timestamp.isdigit():
        return False
    issued_at = int(timestamp)
    current_time = int(time.time()) if now is None else now
    if abs(current_time - issued_at) > _WORKSHOP_PROXY_SIGNATURE_MAX_AGE_SECONDS:
        return False

    expected = create_workshop_proxy_signature(
        method=method,
        path=path,
        timestamp=timestamp,
        instance_id=instance_id,
        user_id=user_id,
    )
    return bool(expected) and hmac.compare_digest(expected, signature)


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any([
        ip.is_private,
        ip.is_loopback,
        ip.is_link_local,
        ip.is_multicast,
        ip.is_reserved,
        ip.is_unspecified,
    ])


def validate_public_http_url(raw_url: str, *, allowed_schemes: Iterable[str] = ("https", "http")) -> str:
    """Validate an outbound URL to reduce SSRF risk."""
    if not raw_url or not isinstance(raw_url, str):
        raise HTTPException(status_code=400, detail="URL不能为空")

    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in set(allowed_schemes):
        raise HTTPException(status_code=400, detail="仅支持 HTTP/HTTPS URL")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL缺少主机名")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URL不允许包含认证信息")

    host = parsed.hostname.strip().rstrip(".")
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise HTTPException(status_code=400, detail="URL不允许指向本机地址")

    try:
        ip = ipaddress.ip_address(host)
        if _is_forbidden_ip(ip):
            raise HTTPException(status_code=400, detail="URL不允许指向内网或保留地址")
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="URL主机名无法解析")
        for info in infos:
            resolved_ip = ipaddress.ip_address(info[4][0])
            if _is_forbidden_ip(resolved_ip):
                raise HTTPException(status_code=400, detail="URL解析到内网或保留地址")

    return raw_url.strip().rstrip("/")
