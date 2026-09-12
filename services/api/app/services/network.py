from pathlib import Path
from urllib.parse import urljoin

import httpx

from .security import UnsafeUrlError, validate_public_url


REDIRECTS = {301, 302, 303, 307, 308}


def _peer_is_public(response: httpx.Response) -> None:
    stream = response.extensions.get("network_stream")
    if stream is None:
        return
    try:
        peer = stream.get_extra_info("server_addr")
        if peer:
            host = f"[{peer[0]}]" if ":" in peer[0] else peer[0]
            validate_public_url(f"https://{host}", resolve_dns=False)
    except (AttributeError, TypeError):
        return


def public_get(url: str, *, timeout: int = 30, max_bytes: int = 10 * 1024 * 1024) -> tuple[str, bytes]:
    current = validate_public_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(6):
            with client.stream("GET", current) as response:
                _peer_is_public(response)
                if response.status_code in REDIRECTS:
                    location = response.headers.get("location")
                    if not location:
                        response.raise_for_status()
                    current = validate_public_url(urljoin(current, location))
                    continue
                response.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Страница превышает безопасный лимит")
                    chunks.append(chunk)
                return str(response.url), b"".join(chunks)
    raise UnsafeUrlError("Слишком много перенаправлений")


def public_download(url: str, target: Path, *, timeout: int, max_bytes: int) -> str:
    current = validate_public_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(6):
            with client.stream("GET", current) as response:
                _peer_is_public(response)
                if response.status_code in REDIRECTS:
                    location = response.headers.get("location")
                    if not location:
                        response.raise_for_status()
                    current = validate_public_url(urljoin(current, location))
                    continue
                response.raise_for_status()
                size = 0
                with target.open("wb") as output:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError("Скачиваемый файл превышает лимит")
                        output.write(chunk)
                return str(response.url)
    raise UnsafeUrlError("Слишком много перенаправлений")
