"""Deterministic provider that replays fixed responses.

Used for tests, offline demonstrations and replaying recorded runs. Responses
are served in order (cycling), or chosen by the first ``match`` substring that
occurs in the prompt.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .base import Completion, ProviderError


class ScriptedProvider:
    def __init__(self, responses: list[str] | None = None, rules: list[tuple[str, str]] | None = None, name: str = "scripted"):
        if not responses and not rules:
            raise ValueError("a scripted provider needs responses or rules")
        self.responses = list(responses or [])
        self.rules = list(rules or [])
        self.name = name
        self.prompts: list[str] = []
        self._next = 0
        self._lock = threading.Lock()

    @classmethod
    def from_file(cls, path: str) -> "ScriptedProvider":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            return cls(responses=[str(r) for r in data], name=f"scripted:{Path(path).name}")
        rules = [(rule["match"], rule["response"]) for rule in data.get("rules", [])]
        return cls(responses=data.get("responses"), rules=rules, name=f"scripted:{Path(path).name}")

    def complete(self, system: str, prompt: str) -> Completion:
        with self._lock:
            self.prompts.append(prompt)
            for match, response in self.rules:
                if match in prompt or match in system:
                    return Completion(text=response, model=self.name, stop_reason="end_turn")
            if not self.responses:
                raise ProviderError("no scripted response matches this prompt")
            response = self.responses[self._next % len(self.responses)]
            self._next += 1
        return Completion(text=response, model=self.name, stop_reason="end_turn")
