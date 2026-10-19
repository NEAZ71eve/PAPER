from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


class CodeExecError(Exception):
    pass


def execute_code(code: str, timeout: float) -> None:
    """子进程执行生成的代码（代码内已含 savefig），失败或超时抛 CodeExecError。"""
    with tempfile.TemporaryDirectory(prefix="chart_exec_") as td:
        script = Path(td) / "chart_code.py"
        script.write_text(code, encoding="utf-8")
        env = dict(os.environ, MPLBACKEND="Agg")
        try:
            proc = subprocess.run(
                [sys.executable, str(script)], capture_output=True, text=True, timeout=timeout, env=env, cwd=td
            )
        except subprocess.TimeoutExpired:
            raise CodeExecError(f"代码执行超时（>{timeout}s）")
        if proc.returncode != 0:
            tail = (proc.stderr or "")[-800:]
            raise CodeExecError(f"代码执行失败:\n{tail}")
