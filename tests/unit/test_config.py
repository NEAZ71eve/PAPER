import os
from chart_sdk.config import Config


def test_defaults():
    c = Config.from_env()
    assert c.base_url == "http://localhost:11434/v1"
    assert c.model == "qwen2.5vl:7b"
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
