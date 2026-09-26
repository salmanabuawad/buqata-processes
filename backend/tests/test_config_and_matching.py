from __future__ import annotations

from app.config import Settings
from app.engines.matching import CategoryRef, match_supplier


def test_list_settings_accept_comma_separated_env(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,10.0.0.1")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test")
    settings = Settings()
    assert settings.trusted_proxies == ["127.0.0.1", "10.0.0.1"]
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_demo_mode_is_never_enabled_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEMO_MODE", "true")
    assert Settings().demo_enabled is False


ROOT = CategoryRef("it", "/it/")
COMPUTERS = CategoryRef("pc", "/it/pc/")
DESKTOP = CategoryRef("desk", "/it/pc/desk/")
LAPTOP = CategoryRef("lap", "/it/pc/lap/")
NETWORK = CategoryRef("net", "/it/net/")


def test_same_branch_matches_both_directions_but_not_siblings():
    assert match_supplier([ROOT], [DESKTOP])[0].relation == "supplier_broader"
    assert match_supplier([DESKTOP], [COMPUTERS])[0].relation == "supplier_narrower"
    assert match_supplier([DESKTOP], [DESKTOP])[0].relation == "exact"
    assert match_supplier([LAPTOP], [DESKTOP]) == []
    assert match_supplier([NETWORK], [DESKTOP]) == []


def test_region_restriction():
    assert match_supplier([DESKTOP], [DESKTOP], ["north"], ["golan"]) == []
    assert match_supplier([DESKTOP], [DESKTOP], ["golan"], ["golan"])
    assert match_supplier([DESKTOP], [DESKTOP], [], [])
