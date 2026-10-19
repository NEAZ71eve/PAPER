from __future__ import annotations

import base64

from openai import OpenAI

from chart_sdk.config import Config


class VLClient:
    """Ollama OpenAI 兼容端点客户端（/v1）。"""

    def __init__(self, config: Config):
        self.config = config
        self._client = OpenAI(base_url=config.base_url, api_key="ollama", timeout=config.vl_timeout)

    def health(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    def model_available(self) -> bool:
        try:
            return any(m.id == self.config.model for m in self._client.models.list())
        except Exception:
            return False

    def chat_image(self, prompt: str, image_bytes: bytes, mime: str = "image/png", max_tokens: int = 2048, temperature: float = 0.1) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }
        last_err: Exception | None = None
        for _ in range(self.config.retry + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.config.model, messages=[message], max_tokens=max_tokens, temperature=temperature
                )
                return resp.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001 - 统一重试
                last_err = e
        raise RuntimeError(f"VL 调用失败: {last_err}")
