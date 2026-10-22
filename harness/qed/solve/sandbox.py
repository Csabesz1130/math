"""Run Python functions in a child process with resource limits.

Each call runs in a fresh interpreter (``python -I``) in an empty temporary
directory, with a minimal environment and limits on CPU time, address space,
file size and open files. This contains accidents and runaway code; it is not
a security boundary. Model-written code only reaches it when the caller passed
``--exec``.
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DRIVER = r"""
import importlib.util, json, sys, time
spec = importlib.util.spec_from_file_location("candidate", "candidate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
entry = getattr(module, sys.argv[1])
argument = json.loads(sys.stdin.read())
start = time.perf_counter()
value = entry() if argument is None else entry(argument)
elapsed = time.perf_counter() - start
sys.stdout.write("\n__QED_RESULT__" + json.dumps({"value": value, "seconds": elapsed}))
"""


@dataclass
class RunResult:
    ok: bool
    value: Any = None
    error: str = ""
    seconds: float = 0.0


def _limits(cpu_seconds: int, memory_mb: int):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        memory = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        os.setsid()

    return apply


def call(source: str, entry: str, argument: Any, *, timeout: float = 20.0, memory_mb: int = 1024) -> RunResult:
    """Call ``entry(argument)`` (or ``entry()`` when argument is None) from
    ``source`` in a sandboxed child process.

    The argument and the return value cross the boundary as JSON.
    """

    with tempfile.TemporaryDirectory(prefix="qed-sandbox-") as work:
        Path(work, "candidate.py").write_text(source, encoding="utf-8")
        Path(work, "driver.py").write_text(_DRIVER, encoding="utf-8")
        start = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "driver.py", entry],
                input=json.dumps(argument),
                capture_output=True,
                text=True,
                cwd=work,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0", "LANG": "C.UTF-8"},
                timeout=timeout,
                preexec_fn=_limits(int(timeout) + 1, memory_mb),
            )
        except subprocess.TimeoutExpired:
            return RunResult(False, error=f"timed out after {timeout:g}s", seconds=time.perf_counter() - start)
        elapsed = time.perf_counter() - start
        marker = completed.stdout.rfind("\n__QED_RESULT__")
        if completed.returncode != 0 or marker < 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            tail = " | ".join(detail[-3:]) if detail else f"exit status {completed.returncode}"
            return RunResult(False, error=tail[:600], seconds=elapsed)
        payload = json.loads(completed.stdout[marker + len("\n__QED_RESULT__"):])
        return RunResult(True, value=payload["value"], seconds=payload["seconds"])
