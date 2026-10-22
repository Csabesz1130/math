"""Model provider interface.

The harness talks to models through one narrow call: a system prompt and a
single user prompt in, text out. Refinement rounds restate the previous
attempt and the verifier feedback in a fresh prompt instead of editing a
conversation, so every request is self-contained and append-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    """A model call failed or was declined; the attempt records it and moves on."""


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None


class Provider(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> Completion: ...


def make_provider(spec: str) -> Provider:
    """Build a provider from a command-line spec.

    - ``anthropic`` or ``anthropic:<model>[@<effort>]``, e.g. ``anthropic:claude-opus-5-5@max``
    - ``openai-compat:<base-url>#<model>`` for an OpenAI-compatible server
      (vLLM, llama.cpp, ...) hosting an open-weight prover; the key, if any, is
      read from ``QED_OPENAI_COMPAT_API_KEY``
    - ``scripted:<file.json>`` replays fixed responses (offline runs and tests)
    """

    kind, _, rest = spec.partition(":")
    if kind == "anthropic":
        from .anthropic_provider import AnthropicProvider

        model, _, effort = rest.partition("@")
        return AnthropicProvider(model=model or None, effort=effort or None)
    if kind == "openai-compat":
        from .openai_compat import OpenAICompatProvider

        base_url, _, model = rest.partition("#")
        if not base_url or not model:
            raise ValueError("openai-compat spec must be openai-compat:<base-url>#<model>")
        return OpenAICompatProvider(base_url=base_url, model=model)
    if kind == "scripted":
        from .scripted import ScriptedProvider

        if not rest:
            raise ValueError("scripted spec must be scripted:<file.json>")
        return ScriptedProvider.from_file(rest)
    raise ValueError(f"unknown provider {spec!r}; expected anthropic, openai-compat or scripted")
