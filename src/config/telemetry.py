"""Langfuse tracing (server v2, Python SDK v2).

One shared client sends events in the background; each graph run gets its own
trace and LangChain callback handler (the handler keeps per-run state, so it
can't be shared by concurrent requests). Disabled while the keys are empty.
"""

import sys
from importlib import import_module
from typing import Any

from config.envs import envs
from config.logging import get_logger

logger = get_logger(__name__)

# SDK v2 imports LangChain 0.x module paths that LangChain 1.x moved to langchain_core.
_LANGCHAIN_ALIASES = {
    "langchain.callbacks.base": "langchain_core.callbacks.base",
    "langchain.schema.agent": "langchain_core.agents",
    "langchain.schema.document": "langchain_core.documents",
    "langchain.load.serializable": "langchain_core.load.serializable",
}

_client = None


def _alias_langchain_modules() -> None:
    for old, new in _LANGCHAIN_ALIASES.items():
        sys.modules.setdefault(old, import_module(new))


def enabled() -> bool:
    return bool(envs.langfuse_public_key and envs.langfuse_secret_key)


def _get_client():
    global _client
    if _client is None:
        _alias_langchain_modules()
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=envs.langfuse_public_key,
            secret_key=envs.langfuse_secret_key,
            host=envs.langfuse_host,
            release=envs.app_env,
        )
        logger.info(f"Langfuse tracing enabled ({envs.langfuse_host})")
    return _client


def trace_callbacks(
    name: str,
    *,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    input: Any = None,
) -> list:
    """Callbacks for one graph run (empty when tracing is disabled).

    Tracing must never break a chat turn: any failure here only logs.
    """
    if not enabled():
        return []
    try:
        trace = _get_client().trace(
            name=name,
            session_id=session_id,
            tags=[envs.app_env, *(tags or [])],
            metadata=metadata,
            input=input,
        )
        # update_parent: the graph's final output becomes the trace output.
        return [trace.get_langchain_handler(update_parent=True)]
    except Exception:  # noqa: BLE001
        logger.exception("Failed to start Langfuse trace")
        return []


def flush() -> None:
    """Sends the queued events (call on shutdown)."""
    if _client is not None:
        _client.flush()
