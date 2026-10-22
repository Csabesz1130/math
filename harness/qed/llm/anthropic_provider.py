"""Claude through the official Anthropic SDK (``pip install anthropic``)."""

from __future__ import annotations

from .base import Completion, ProviderError

DEFAULT_MODEL = "claude-opus-5-5"
# Mathematical reasoning is intelligence-sensitive: start at high and raise to
# max per run (``anthropic:claude-opus-5-5@max``) when the problem warrants it.
DEFAULT_EFFORT = "high"
MAX_TOKENS = 64000
# Models that accept the server-side refusal fallback in its "default" form.
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    def __init__(self, model: str | None = None, effort: str | None = None, max_tokens: int = MAX_TOKENS):
        try:
            import anthropic
        except ImportError as error:
            raise ProviderError("the anthropic provider needs the SDK: pip install anthropic") from error
        self._anthropic = anthropic
        # Credentials resolve from ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or an
        # `ant auth login` profile.
        self.client = anthropic.Anthropic()
        self.model = model or DEFAULT_MODEL
        self.effort = effort or DEFAULT_EFFORT
        self.max_tokens = max_tokens
        self.name = f"anthropic:{self.model}@{self.effort}"

    def complete(self, system: str, prompt: str) -> Completion:
        anthropic = self._anthropic
        request = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
        )
        try:
            # Streaming keeps long reasoning turns clear of HTTP timeouts.
            if self.model in _FALLBACK_MODELS:
                stream = self.client.beta.messages.stream(
                    **request, betas=[_FALLBACK_BETA], fallbacks="default"
                )
            else:
                stream = self.client.messages.stream(**request)
            with stream as events:
                message = events.get_final_message()
        except anthropic.RateLimitError as error:
            raise ProviderError(f"rate limited by the Anthropic API: {error.message}") from error
        except anthropic.APIStatusError as error:
            raise ProviderError(f"Anthropic API error {error.status_code}: {error.message}") from error
        except anthropic.APIConnectionError as error:
            raise ProviderError(f"could not reach the Anthropic API: {error}") from error

        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise ProviderError(f"the model declined the request (category: {category})")
        text = "".join(block.text for block in message.content if block.type == "text")
        if message.stop_reason == "max_tokens":
            text += "\n\n[truncated: the response reached max_tokens]"
        usage = message.usage
        return Completion(
            text=text,
            model=message.model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            stop_reason=message.stop_reason,
        )
