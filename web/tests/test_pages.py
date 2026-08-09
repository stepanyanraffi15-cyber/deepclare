"""Every page renders standalone — no network, no other components involved."""

import pytest
from deepclare_web.app import create_app
from deepclare_web.config import SiteConfig
from fastapi.testclient import TestClient

PAGES = ["/", "/terms", "/privacy", "/refund", "/contact"]


def make_client(**overrides: str) -> TestClient:
    return TestClient(create_app(SiteConfig(**overrides)))


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(path: str) -> None:
    response = make_client().get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_healthz() -> None:
    assert make_client().get("/healthz").json() == {"status": "ok"}


def test_unknown_path_renders_armenian_404_page() -> None:
    response = make_client().get("/nope")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "Էջը չի գտնվել" in response.text


def test_config_reads_web_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_CONTACT_PHONE", "+374 10 000000")
    monkeypatch.setenv("WEB_COMPANY_UNN", "01234567")
    config = SiteConfig.from_env()
    assert config.contact_phone == "+374 10 000000"
    assert config.company_unn == "01234567"


def test_config_ignores_changeme_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_COMPANY_LEGAL_NAME", "changeme")
    assert SiteConfig.from_env().company_legal_name == "DeepClare"


def test_try_section_and_script_served() -> None:
    client = make_client()
    html = client.get("/").text
    assert 'id="try"' in html
    assert "/static/demo.js" in html
    response = client.get("/static/demo.js")
    assert response.status_code == 200
    assert "ESADout_CU" in response.text


def test_chrome_store_link_rendered_and_configurable() -> None:
    assert "chromewebstore.google.com" in make_client().get("/").text
    html = make_client(chrome_store_url="https://example.com/ext").get("/").text
    assert "https://example.com/ext" in html
    assert "chromewebstore.google.com" not in html


def test_canonical_link_only_with_https_base_url() -> None:
    html = make_client(base_url="https://example.am").get("/contact").text
    assert '<link rel="canonical" href="https://example.am/contact">' in html
    assert "canonical" not in make_client().get("/contact").text


def test_optional_contact_rows_absent_when_unset() -> None:
    html = make_client(contact_phone="", telegram_link="").get("/contact").text
    assert "tel:" not in html
    assert "Telegram" not in html


def test_try_demo_has_no_customs_outcome_guarantee() -> None:
    html = make_client().get("/").text
    assert 'id="try-result"' in html
    assert "Կանաչ միջանցք" not in html
    assert 'id="try-corridor"' not in html


@pytest.mark.parametrize("path", PAGES)
def test_journey_scene_has_three_risk_channel_lights(path: str) -> None:
    html = make_client().get(path).text
    assert "j-light-red" in html
    assert "j-light-yellow" in html
    assert "j-light-green" in html
