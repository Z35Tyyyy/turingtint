"""Lazy guided JSON decoding without the dependency's passage-bearing logs.

The pinned lm-format-enforcer 0.11.3 token enforcer logs the complete prompt on
an internal parser failure, then permits EOS. Suppress only that module's local
logging binding: ordinary application/root logging must remain available.
Callers must still reject incomplete or invalid generated output.
"""
from __future__ import annotations


class _PrivateTokenEnforcerLogging:
    """The three logging calls used by the pinned token-enforcer module.

    Do not retain messages or exception arguments: either can contain submitted
    text. Unexpected new dependency logging APIs fail closed rather than falling
    back to a real logger. This object is not installed into Python's logging
    module or any application logger.
    """

    ERROR = 40

    @staticmethod
    def basicConfig(*_args, **_kwargs):
        return None

    @staticmethod
    def debug(*_args, **_kwargs):
        return None

    @staticmethod
    def exception(*_args, **_kwargs):
        return None


_PRIVATE_LOGGING = _PrivateTokenEnforcerLogging()


def build_prefix_constraint(tokenizer, schema):
    """Return a fresh LMFE prefix function; import ML dependencies only on use.

    ``tokenizer`` also accepts LMFE's reusable TokenEnforcerTokenizerData. The
    parser and generation state are new for every call. The privacy binding is
    intentionally permanent for the process, so another concurrent request
    cannot restore passage logging during an active generation.
    """
    import lmformatenforcer.tokenenforcer as token_enforcer

    # Assign before constructing/using any enforcer. This changes only the
    # dependency module's name binding, never logging.disable or root handlers.
    token_enforcer.logging = _PRIVATE_LOGGING

    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.integrations.transformers import (
        build_transformers_prefix_allowed_tokens_fn,
    )

    return build_transformers_prefix_allowed_tokens_fn(
        tokenizer, JsonSchemaParser(schema)
    )
