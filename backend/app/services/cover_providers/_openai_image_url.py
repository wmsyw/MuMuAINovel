from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import urlparse, urlsplit, urlunsplit

from fastapi import HTTPException


@dataclass(frozen=True, slots=True)
class PinnedImageUrl:
    fetch_url: str
    log_url: str
    host_header: str | None
    sni_hostname: str | None


def resolve_public_image_url(raw_url: str) -> PinnedImageUrl:
    if not raw_url:
        raise HTTPException(status_code=400, detail="URL不能为空")

    stripped_url = raw_url.strip()
    parsed = urlparse(stripped_url)
    if parsed.scheme not in {"https", "http"}:
        raise HTTPException(status_code=400, detail="仅支持 HTTP/HTTPS URL")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL缺少主机名")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URL不允许包含认证信息")

    host = parsed.hostname.strip().rstrip(".")
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise HTTPException(status_code=400, detail="URL不允许指向本机地址")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolved_ip = _resolve_and_validate_public_ip(host=host, port=port)
    fetch_netloc = _netloc_for_host(host=str(resolved_ip), port=parsed.port)
    fetch_url = urlunsplit((parsed.scheme, fetch_netloc, parsed.path or "/", parsed.query, ""))
    host_header = None
    sni_hostname = None
    if host != str(resolved_ip):
        host_header = _netloc_for_host(host=host, port=parsed.port)
        sni_hostname = host if parsed.scheme == "https" else None

    return PinnedImageUrl(
        fetch_url=fetch_url,
        log_url=sanitize_url_for_log(stripped_url),
        host_header=host_header,
        sni_hostname=sni_hostname,
    )


def sanitize_url_for_log(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<invalid-url>"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _resolve_and_validate_public_ip(
    *,
    host: str,
    port: int,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="URL主机名无法解析")

        resolved_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for info in infos:
            resolved_ip = ipaddress.ip_address(info[4][0])
            if resolved_ip not in resolved_ips:
                resolved_ips.append(resolved_ip)
        if not resolved_ips:
            raise HTTPException(status_code=400, detail="URL主机名无法解析")
        for resolved_ip in resolved_ips:
            if _is_forbidden_ip(resolved_ip):
                raise HTTPException(status_code=400, detail="URL解析到内网或保留地址")
        return resolved_ips[0]

    if _is_forbidden_ip(ip):
        raise HTTPException(status_code=400, detail="URL不允许指向内网或保留地址")
    return ip


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not ip.is_global or ip.is_multicast


def _netloc_for_host(*, host: str, port: int | None) -> str:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        host_part = host
    else:
        host_part = f"[{host}]" if ip.version == 6 else host
    return f"{host_part}:{port}" if port is not None else host_part
