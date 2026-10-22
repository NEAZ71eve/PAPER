import os
from chart_sdk.config import Config


def test_defaults():
    c = Config.from_env()
    assert c.base_url == "http://localhost:11434/v1"
    assert c.model == "qwen2.5vl:3b"
    assert c.dpi == 150
    assert c.max_pages == 30
    assert c.exec_timeout == 30.0
    assert c.vl_timeout == 120.0


def test_env_override(monkeypatch):
    monkeypatch.setenv("CHART_SDK_MODEL", "qwen2.5vl:3b")
    monkeypatch.setenv("CHART_SDK_DPI", "200")
    c = Config.from_env()
    assert c.model == "qwen2.5vl:3b"
    assert c.dpi == 200


def test_api_port_default(monkeypatch):
    monkeypatch.delenv("CHART_SDK_API_PORT", raising=False)
    assert Config.from_env().api_port == 8000


def test_api_port_override(monkeypatch):
    monkeypatch.setenv("CHART_SDK_API_PORT", "9000")
    assert Config.from_env().api_port == 9000
