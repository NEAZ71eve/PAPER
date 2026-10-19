from __future__ import annotations

from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.vision.json_utils import extract_json
from chart_sdk.vision.prompts import PARSE_PROMPT
from chart_sdk.vision.validator import ValidationError, validate_chart


class ParseError(Exception):
    pass


def parse_chart(client: VLClient, image_bytes: bytes, mime: str = "image/png", config: Config | None = None) -> dict:
    """调 VL 解析单张图表图 → 校验；失败重试 1 次（设计文档 7）。"""
    retry = config.retry if config else 1
    last: Exception | None = None
    for attempt in range(retry + 1):
        resp = client.chat_image(PARSE_PROMPT, image_bytes, mime=mime)
        data = extract_json(resp)
        if data is None:
            last = ParseError("模型输出中没有 JSON")
            continue
        try:
            chart, _ = validate_chart(data)
            return chart
        except ValidationError as e:
            last = e
    raise ParseError(f"解析失败（含重试）: {last}")
