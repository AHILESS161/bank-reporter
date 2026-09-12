import httpx
import pytest

from app.services import network
from app.services.network import public_get
from app.services.security import (
    UnsafeUrlError,
    canonical_url,
    normalized_title,
    safe_filename,
    validate_public_url,
)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/admin", "http://localhost:8000"])
def test_private_urls_are_rejected(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url, resolve_dns=False)


def test_public_https_syntax_is_allowed_without_dns():
    assert validate_public_url("https://www.cbr.ru/statistics/", resolve_dns=False).startswith("https://")


def test_names_are_normalized():
    assert safe_filename("../опасный<>отчет.pdf") == "опасный_отчет.pdf"
    assert normalized_title("Банк: отчет — 2026") == "банк отчет 2026"


def test_canonical_url_removes_tracking_and_fragment():
    assert (
        canonical_url("HTTPS://Example.COM/report/?utm_source=yandex&year=2026#table")
        == "https://example.com/report?year=2026"
    )


def test_redirect_to_private_ip_is_rejected_before_second_request(monkeypatch, respx_mock):
    def validate(url: str, **_):
        if "127.0.0.1" in url:
            raise UnsafeUrlError("private")
        return url

    monkeypatch.setattr(network, "validate_public_url", validate)
    route = respx_mock.get("https://public.example/start").mock(
        return_value=httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
    )
    with pytest.raises(UnsafeUrlError):
        public_get("https://public.example/start")
    assert route.call_count == 1
