import base64
from unittest.mock import MagicMock

from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient


def _client():
    cfg = Config.from_env()
    return VLClient(cfg)


def test_chat_image_builds_data_url(monkeypatch):
    c = _client()
    fake_openai = MagicMock()
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        msg = MagicMock()
        msg.choices = [MagicMock()]
        msg.choices[0].message.content = "hello"
        resp = MagicMock()
        resp.__getitem__ = lambda self, i: msg.choices[i] if False else None
        wrapper = MagicMock()
        wrapper.choices = msg.choices
        wrapper.message = msg.choices[0].message
        fake_openai.chat.completions.create = fake_create
        return wrapper

    fake_openai.chat.completions.create = fake_create
    monkeypatch.setattr(c, "_client", fake_openai)
    out = c.chat_image("p", b"img")
    assert out == "hello"
    parts = captured["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "p"}
    b64 = base64.b64encode(b"img").decode()
    assert parts[1]["image_url"]["url"] == f"data:image/png;base64,{b64}"


def test_health_true_and_false(monkeypatch):
    c = _client()
    ok = MagicMock()
    ok.models.list.return_value = []
    bad = MagicMock()
    bad.models.list.side_effect = RuntimeError("down")
    monkeypatch.setattr(c, "_client", ok)
    assert c.health() is True
    monkeypatch.setattr(c, "_client", bad)
    assert c.health() is False


def test_chat_image_retries_then_succeeds(monkeypatch):
    c = _client()
    fake = MagicMock()
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        msg = MagicMock()
        msg.choices = [MagicMock()]
        msg.choices[0].message.content = "ok"
        return msg

    fake.chat.completions.create = flaky
    monkeypatch.setattr(c, "_client", fake)
    assert c.chat_image("p", b"img") == "ok"
    assert calls["n"] == 2
