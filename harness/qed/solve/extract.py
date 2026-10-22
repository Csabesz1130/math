"""Pull the checkable part out of a model's response."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```([A-Za-z0-9_+-]*)[^\n]*\n(.*?)```", re.S)
_ANSWER = re.compile(r"(?:^|\s)\**ANSWER\**\s*:\s*(.+?)\s*$", re.M)


def fenced(text: str, *languages: str) -> str | None:
    """The last fenced block whose language is one of ``languages``."""

    blocks = [body for lang, body in _FENCE.findall(text) if lang.lower() in languages]
    return blocks[-1].strip("\n") if blocks else None


def final_answer(text: str) -> str | None:
    answers = _ANSWER.findall(text)
    if answers:
        return answers[-1].strip().strip("$").strip()
    boxed = _last_boxed(text)
    return boxed.strip() if boxed is not None else None


def _last_boxed(text: str) -> str | None:
    start = text.rfind("\\boxed{")
    if start < 0:
        return None
    depth, i = 1, start + len("\\boxed{")
    begin = i
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[begin : i - 1] if depth == 0 else None


def json_object(text: str) -> Any:
    """The last ```json block, parsed; raises ValueError when there is none."""

    block = fenced(text, "json")
    if block is None:
        raise ValueError("the response has no ```json block")
    try:
        return json.loads(block)
    except json.JSONDecodeError as error:
        raise ValueError(f"the ```json block does not parse: {error}") from error


def python_module(text: str) -> str:
    block = fenced(text, "python", "py")
    if block is None:
        raise ValueError("the response has no ```python block")
    return block


def lean_proof(text: str) -> str:
    block = fenced(text, "lean", "lean4")
    if block is None:
        raise ValueError("the response has no ```lean block")
    return block
