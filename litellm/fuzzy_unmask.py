"""Tolerant un-masking for LiteLLM (post_call guardrail).

The presidio guardrail restores `<PERSON_1>` only when the model echoes the
placeholder byte for byte. Models often rewrite it as `[PERSON_1]`, `{PERSON_1}`
or bare `PERSON_1`. This hook runs after the model call, reads the per-request
`pii_tokens` map the presidio guardrail stored, and restores every such spelling
in the answer text, tool-call arguments and Anthropic-format content blocks.

Config (litellm/config.yaml):
    - guardrail_name: pii-unmask-tolerant
      litellm_params:
        guardrail: fuzzy_unmask.FuzzyUnmask
        mode: post_call
        default_on: true
"""

from __future__ import annotations

import re
from typing import Any, AsyncGenerator

from litellm.integrations.custom_guardrail import CustomGuardrail
from litellm.proxy._types import UserAPIKeyAuth
from litellm.types.guardrails import GuardrailEventHooks

PLACEHOLDER_LIKE = re.compile(r"(?:[<\[{(]\s*)?\b([A-Z][A-Z_]*_\d+)\b(?:\s*[>\]})])?")


def restore(text: str, tokens: dict[str, str]) -> str:
    if not text or not tokens:
        return text

    def repl(m: re.Match[str]) -> str:
        key = f"<{m.group(1)}>"
        return tokens.get(key, m.group(0))

    return PLACEHOLDER_LIKE.sub(repl, text)


def _tokens(data: dict | None) -> dict[str, str]:
    return ((data or {}).get("metadata") or {}).get("pii_tokens") or {}


def _restore_openai(response: Any, tokens: dict[str, str]) -> None:
    for choice in getattr(response, "choices", None) or []:
        message = getattr(choice, "message", None)
        if message is None:
            continue
        content = getattr(message, "content", None)
        if isinstance(content, str):
            message.content = restore(content, tokens)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    part["text"] = restore(part["text"], tokens)
        for call in getattr(message, "tool_calls", None) or []:
            fn = getattr(call, "function", None)
            if fn is not None and isinstance(getattr(fn, "arguments", None), str):
                fn.arguments = restore(fn.arguments, tokens)


def _restore_anthropic(response: dict, tokens: dict[str, str]) -> None:
    for block in response.get("content") or []:
        if isinstance(block, dict):
            if isinstance(block.get("text"), str):
                block["text"] = restore(block["text"], tokens)
            if isinstance(block.get("input"), str):
                block["input"] = restore(block["input"], tokens)


class FuzzyUnmask(CustomGuardrail):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("supported_event_hooks", [GuardrailEventHooks.post_call])
        super().__init__(**kwargs)

    async def async_post_call_success_hook(self, data: dict, user_api_key_dict: UserAPIKeyAuth, response: Any) -> Any:
        if self.should_run_guardrail(data=data, event_type=GuardrailEventHooks.post_call) is not True:
            return response
        tokens = _tokens(data)
        if not tokens:
            return response
        if isinstance(response, dict) and response.get("type") == "message":
            _restore_anthropic(response, tokens)
        else:
            _restore_openai(response, tokens)
        return response

    async def async_post_call_streaming_iterator_hook(
        self, user_api_key_dict: UserAPIKeyAuth, response: Any, request_data: dict
    ) -> AsyncGenerator[Any, None]:
        tokens = _tokens(request_data)
        if not tokens:
            async for item in response:
                yield item
            return
        # A placeholder may be split across chunks: collect the stream, restore the whole
        # text once, hand it back in the first content chunk (the presidio guardrail
        # buffers the same way, so the client already sees one final chunk).
        chunks: list[Any] = []
        async for item in response:
            chunks.append(item)
        pieces: list[str] = []
        first_text_chunk = None
        for item in chunks:
            for choice in getattr(item, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                content = getattr(delta, "content", None) if delta is not None else None
                if isinstance(content, str) and content:
                    pieces.append(content)
                    if first_text_chunk is None:
                        first_text_chunk = choice
                    else:
                        delta.content = ""
        if first_text_chunk is not None:
            first_text_chunk.delta.content = restore("".join(pieces), tokens)
        for item in chunks:
            yield item
