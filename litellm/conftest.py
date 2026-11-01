"""The hook imports LiteLLM's base classes, which the test venv does not carry: stub the three
modules so the pure restore functions can be tested without the proxy installed."""

import sys
import types


def _module(name: str, **attrs: object) -> None:
    if name in sys.modules:
        return
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod


class _CustomGuardrail:
    def __init__(self, **kwargs: object) -> None:
        pass


class _GuardrailEventHooks:
    post_call = "post_call"


_module("litellm")
_module("litellm.integrations")
_module("litellm.integrations.custom_guardrail", CustomGuardrail=_CustomGuardrail)
_module("litellm.proxy")
_module("litellm.proxy._types", UserAPIKeyAuth=object)
_module("litellm.types")
_module("litellm.types.guardrails", GuardrailEventHooks=_GuardrailEventHooks)
