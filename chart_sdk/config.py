import os
from dataclasses import dataclass


@dataclass
class Config:
    base_url: str
    model: str
    dpi: int
    max_pages: int
    exec_timeout: float
    vl_timeout: float
    cache_dir: str
    retry: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            base_url=os.getenv("CHART_SDK_BASE_URL", "http://localhost:11434/v1"),
            model=os.getenv("CHART_SDK_MODEL", "qwen2.5vl:7b"),
            dpi=int(os.getenv("CHART_SDK_DPI", "150")),
            max_pages=int(os.getenv("CHART_SDK_MAX_PAGES", "30")),
            exec_timeout=float(os.getenv("CHART_SDK_EXEC_TIMEOUT", "30")),
            vl_timeout=float(os.getenv("CHART_SDK_VL_TIMEOUT", "120")),
            cache_dir=os.getenv("CHART_SDK_CACHE_DIR", "data/cache"),
            retry=1,
        )
