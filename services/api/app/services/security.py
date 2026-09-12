import hashlib
import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


class UnsafeUrlError(ValueError):
    pass


def validate_public_url(url: str, *, resolve_dns: bool = True) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("Разрешены только публичные HTTP(S) URL")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise UnsafeUrlError("Локальные адреса запрещены")
    try:
        direct = ipaddress.ip_address(host)
        if not direct.is_global:
            raise UnsafeUrlError("Непубличный IP-адрес запрещен")
    except ValueError as exc:
        if isinstance(exc, UnsafeUrlError):
            raise
        if resolve_dns:
            try:
                addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443)}
            except socket.gaierror as dns_error:
                raise UnsafeUrlError("Не удалось разрешить имя источника") from dns_error
            if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
                raise UnsafeUrlError("Источник разрешается в непубличную сеть")
    return url


def safe_filename(value: str, fallback: str = "document") -> str:
    name = Path(value).name
    name = re.sub(r"[^\w.()\- ]+", "_", name, flags=re.UNICODE).strip(" .")
    return name[:180] or fallback


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def domain_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def normalized_title(value: str) -> str:
    return re.sub(r"\W+", " ", value.lower(), flags=re.UNICODE).strip()


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    ignored = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "yclid", "gclid"}
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parsed.query) if key.casefold() not in ignored]
    )
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.casefold(), parsed.netloc.casefold(), path, "", query, ""))
