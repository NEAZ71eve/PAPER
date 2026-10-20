from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_session_locks: dict[str, threading.Lock] = {}
_session_locks_guard = threading.Lock()


def _session_lock(pdf_hash: str) -> threading.Lock:
    with _session_locks_guard:
        lk = _session_locks.get(pdf_hash)
        if lk is None:
            lk = threading.Lock()
            _session_locks[pdf_hash] = lk
        return lk


def _atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class PaperStore:
    """论文会话缓存：data/cache/papers/<sha256>/（设计文档 5.3、6.1 第 1 步）。"""

    def __init__(self, cache_dir, pdf_bytes: bytes, file_name: str):
        cache_dir = Path(cache_dir)
        self.pdf_hash = content_hash(pdf_bytes)
        self.root = cache_dir / "papers" / self.pdf_hash
        (self.root / "pages").mkdir(parents=True, exist_ok=True)
        (self.root / "figures").mkdir(exist_ok=True)
        src = self.root / "source.pdf"
        if not src.exists():
            src.write_bytes(pdf_bytes)
        sp = self.root / "session.json"
        with _session_lock(self.pdf_hash):
            if sp.exists():
                self.session = json.loads(sp.read_text(encoding="utf-8"))
            else:
                self.session = {
                    "pdf_hash": self.pdf_hash, "file_name": file_name, "n_pages": 0, "dpi": 0,
                    "stage": "detecting", "pages": [], "figures": [],
                }

    @classmethod
    def open(cls, cache_dir, pdf_hash: str) -> "PaperStore":
        """按 hash 重开已有会话（阅读器 API 用）；不存在抛 KeyError。"""
        obj = cls.__new__(cls)
        obj.pdf_hash = pdf_hash
        obj.root = Path(cache_dir) / "papers" / pdf_hash
        sp = obj.root / "session.json"
        with _session_lock(pdf_hash):
            if not sp.exists():
                raise KeyError(f"会话不存在: {pdf_hash}")
            obj.session = json.loads(sp.read_text(encoding="utf-8"))
        return obj

    def save(self) -> None:
        with _session_lock(self.pdf_hash):
            _atomic_write_json(self.root / "session.json", self.session)

    def figure_dir(self, fig_id: str) -> Path:
        d = self.root / "figures" / fig_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def page_png(self, page_no: int) -> Path:
        for p in self.session["pages"]:
            if p["page"] == page_no:
                return self.root / p["png_path"]
        raise KeyError(f"页面未渲染: {page_no}")


class SingleStore:
    """单图缓存：data/cache/singles/<sha256>/。"""

    def __init__(self, cache_dir, image_bytes: bytes, file_name: str):
        cache_dir = Path(cache_dir)
        self.image_hash = content_hash(image_bytes)
        self.root = cache_dir / "singles" / self.image_hash
        self.root.mkdir(parents=True, exist_ok=True)
        rp = self.root / "record.json"
        if rp.exists():
            self.record = json.loads(rp.read_text(encoding="utf-8"))
        else:
            self.record = {"file_name": file_name, "status": "pending"}

    def save(self) -> None:
        _atomic_write_json(self.root / "record.json", self.record)
