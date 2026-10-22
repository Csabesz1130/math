"""Open-weight models behind an OpenAI-compatible chat-completions server.

This lets a run pair a general reasoning model with a specialised open-weight
prover (for example a Lean prover served by vLLM) in another role.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import Completion, ProviderError

API_KEY_ENV = "QED_OPENAI_COMPAT_API_KEY"


class OpenAICompatProvider:
    def __init__(self, base_url: str, model: str, max_tokens: int = 32000, timeout: float = 1800.0):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.name = f"openai-compat:{model}"

    def complete(self, system: str, prompt: str) -> Completion:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            }
        ).encode()
        headers = {"Content-Type": "application/json"}
        if os.environ.get(API_KEY_ENV):
            headers["Authorization"] = f"Bearer {os.environ[API_KEY_ENV]}"
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            raise ProviderError(f"{self.url} returned HTTP {error.code}: {error.read()[:300]!r}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ProviderError(f"could not reach {self.url}: {error}") from error
        try:
            choice = payload["choices"][0]
            text = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError(f"unexpected response shape from {self.url}") from error
        usage = payload.get("usage") or {}
        return Completion(
            text=text,
            model=payload.get("model", self.model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=choice.get("finish_reason"),
        )
