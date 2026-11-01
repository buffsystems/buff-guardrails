"""Tolerant un-masking for LiteLLM (post_call guardrail).

The presidio guardrail restores `<PERSON_1>` only when the model echoes the
placeholder byte for byte, and on a streamed Responses API call only in the
final `response.completed` event. Models often rewrite it as `[PERSON_1]`,
`{PERSON_1}` or bare `PERSON_1`, and clients such as Codex render the deltas,
not the final event. This hook runs after the model call, reads the per-request
`pii_tokens` map the presidio guardrail stored, and restores every such spelling
in the answer text and tool-call arguments of all three response shapes:
OpenAI chat completions, Anthropic messages and the OpenAI Responses API,
plain and streamed.

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

DELTA_EVENTS = ("response.output_text.delta", "response.function_call_arguments.delta",
                "response.reasoning_summary_text.delta", "response.reasoning_text.delta")
TEXT_DONE_EVENTS = ("response.output_text.done", "response.reasoning_summary_text.done", "response.reasoning_text.done")
PART_DONE_EVENTS = ("response.content_part.done", "response.reasoning_summary_part.done")
TERMINAL_EVENTS = ("response.completed", "response.incomplete")


def restore(text: str, tokens: dict[str, str]) -> str:
    if not text or not tokens:
        return text

    def repl(m: re.Match[str]) -> str:
        key = f"<{m.group(1)}>"
        return tokens.get(key, m.group(0))

    return PLACEHOLDER_LIKE.sub(repl, text)


def _tokens(data: dict | None) -> dict[str, str]:
    return ((data or {}).get("metadata") or {}).get("pii_tokens") or {}


def _get(obj: Any, key: str) -> Any:
    """Field of a dict or an attribute of a pydantic object — LiteLLM hands us both."""
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _set(obj: Any, key: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)


def _kind(event: Any) -> str:
    """The event type as plain text — LiteLLM types it as a str-Enum, whose str() is the member name."""
    kind = _get(event, "type")
    return str(getattr(kind, "value", kind) or "")


def _restore_field(obj: Any, key: str, tokens: dict[str, str]) -> None:
    value = _get(obj, key) if obj is not None else None
    if isinstance(value, str):
        _set(obj, key, restore(value, tokens))


def _restore_openai(response: Any, tokens: dict[str, str]) -> None:
    for choice in _get(response, "choices") or []:
        message = _get(choice, "message")
        if message is None:
            continue
        content = _get(message, "content")
        if isinstance(content, str):
            _set(message, "content", restore(content, tokens))
        elif isinstance(content, list):
            for part in content:
                _restore_field(part, "text", tokens)
        for call in _get(message, "tool_calls") or []:
            _restore_field(_get(call, "function"), "arguments", tokens)


def _restore_anthropic(response: dict, tokens: dict[str, str]) -> None:
    for block in response.get("content") or []:
        _restore_field(block, "text", tokens)
        _restore_field(block, "input", tokens)


def _restore_output_item(item: Any, tokens: dict[str, str]) -> None:
    """One Responses API output item: a message's text parts, a reasoning item's summary
    (clients show it to the user) or a function call's arguments."""
    if item is None:
        return
    for part in (_get(item, "content") or []) + (_get(item, "summary") or []):
        _restore_field(part, "text", tokens)
    _restore_field(item, "arguments", tokens)


def _restore_responses(response: Any, tokens: dict[str, str]) -> None:
    for item in _get(response, "output") or []:
        _restore_output_item(item, tokens)


def restore_response(response: Any, tokens: dict[str, str]) -> None:
    """A whole (non-streamed) response of any of the three shapes, restored in place."""
    if isinstance(response, dict) and response.get("type") == "message":
        _restore_anthropic(response, tokens)
    elif _get(response, "output") is not None:
        _restore_responses(response, tokens)
    else:
        _restore_openai(response, tokens)


def restore_chat_chunks(chunks: list[Any], tokens: dict[str, str]) -> None:
    """A placeholder may be split across chunks: restore the whole text once and hand it
    back in the first content chunk (the presidio guardrail buffers the same way, so the
    client already sees one final chunk)."""
    pieces: list[str] = []
    first: Any = None
    for chunk in chunks:
        for choice in _get(chunk, "choices") or []:
            delta = _get(choice, "delta")
            content = _get(delta, "content") if delta is not None else None
            if isinstance(content, str) and content:
                pieces.append(content)
                if first is None:
                    first = delta
                else:
                    _set(delta, "content", "")
    if first is not None:
        _set(first, "content", restore("".join(pieces), tokens))


def restore_responses_events(events: list[Any], tokens: dict[str, str]) -> None:
    """Responses API stream: deltas are joined per output part (a placeholder may be split
    across them), restored once and handed back in the part's first delta; the `done`
    events and the terminal event carry whole texts and are restored in place."""
    groups: dict[tuple, list[Any]] = {}
    for event in events:
        kind = _kind(event)
        if kind in DELTA_EVENTS:
            key = (kind, _get(event, "item_id"), _get(event, "output_index"),
                   _get(event, "content_index"), _get(event, "summary_index"))
            groups.setdefault(key, []).append(event)
        elif kind in TEXT_DONE_EVENTS:
            _restore_field(event, "text", tokens)
        elif kind == "response.function_call_arguments.done":
            _restore_field(event, "arguments", tokens)
        elif kind in PART_DONE_EVENTS:
            _restore_field(_get(event, "part"), "text", tokens)
        elif kind == "response.output_item.done":
            _restore_output_item(_get(event, "item"), tokens)
        elif kind in TERMINAL_EVENTS:
            _restore_responses(_get(event, "response"), tokens)
    for group in groups.values():
        whole = restore("".join(_get(e, "delta") or "" for e in group), tokens)
        for e in group:
            _set(e, "delta", "")
        _set(group[0], "delta", whole)


def _is_responses_stream(chunks: list[Any]) -> bool:
    return bool(chunks) and _kind(chunks[0]).startswith("response.")


class FuzzyUnmask(CustomGuardrail):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("supported_event_hooks", [GuardrailEventHooks.post_call])
        super().__init__(**kwargs)

    async def async_post_call_success_hook(self, data: dict, user_api_key_dict: UserAPIKeyAuth, response: Any) -> Any:
        if self.should_run_guardrail(data=data, event_type=GuardrailEventHooks.post_call) is not True:
            return response
        tokens = _tokens(data)
        if tokens:
            restore_response(response, tokens)
        return response

    async def async_post_call_streaming_iterator_hook(
        self, user_api_key_dict: UserAPIKeyAuth, response: Any, request_data: dict
    ) -> AsyncGenerator[Any, None]:
        tokens = _tokens(request_data)
        if not tokens:
            async for item in response:
                yield item
            return
        chunks = [item async for item in response]
        if _is_responses_stream(chunks):
            restore_responses_events(chunks, tokens)
        else:
            restore_chat_chunks(chunks, tokens)
        for item in chunks:
            yield item
