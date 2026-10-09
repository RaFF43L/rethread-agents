"""Chat business logic — transport framework agnostic.

Exposes two consumption forms:
- `process_chat`: blocking, returns the complete `ChatResponse`.
- `process_chat_stream`: async generator of SSE events (lifecycle + final text).
"""

import asyncio
import json
from typing import Any, AsyncGenerator

from actions.base import ChatRequest, ChatResponse
from ai.agent import GRAPH_NAME, rethread_agent
from ai.states import INTENT_ORDER
from catalog.db import session_scope
from config.envs import envs
from config.logging import get_logger
from sessions import repository as sessions_repository

logger = get_logger(__name__)


def _graph_input(request: ChatRequest) -> dict[str, Any]:
    """Graph input. With a session: merges the stored context and loads the history."""
    measurements = (
        request.buyer_measurements.model_dump(exclude_none=True)
        if request.buyer_measurements
        else {}
    )
    if not request.session_id:
        return {
            "message": request.message,
            "item_id": request.item_id,
            "buyer_measurements": measurements,
            "history": [],
        }

    with session_scope() as session:
        chat = sessions_repository.open_session(
            session, request.session_id, request.item_id, measurements
        )
        history = sessions_repository.recent_messages(
            session, chat.id, limit=envs.chat_history_messages
        )
        return {
            "message": request.message,
            "item_id": chat.item_id,
            "buyer_measurements": dict(chat.buyer_measurements or {}),
            "history": [sessions_repository.message_to_dict(m) for m in history],
        }


def _save_turn(request: ChatRequest, graph_input: dict[str, Any], state: dict[str, Any]) -> None:
    """Stores the turn in the session. A failure here must not lose the answer."""
    if not request.session_id or not state.get("response"):
        return
    try:
        with session_scope() as session:
            sessions_repository.save_turn(
                session,
                request.session_id,
                message=request.message,
                response=state["response"],
                item_id=graph_input.get("item_id"),
                skus=state.get("skus", []),
            )
    except Exception:  # noqa: BLE001
        logger.exception(f"Failed to save turn of session {request.session_id}")


def _to_response(state: dict[str, Any], session_id: str | None = None) -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        intents=state.get("intents", []),
        reasoning=state.get("reasoning", ""),
        response=state.get("response", ""),
        skus=state.get("skus", []),
        agent_outputs=state.get("agent_outputs", {}),
        metadata=state.get("metadata", {}),
    )


async def process_chat(request: ChatRequest) -> ChatResponse:
    """Executes the graph for a message and returns the result."""
    logger.info(f"Processing chat: {request.message[:80]}")
    graph_input = await asyncio.to_thread(_graph_input, request)
    result = await rethread_agent.ainvoke(
        graph_input,
        config={"recursion_limit": envs.recursion_limit},
    )
    await asyncio.to_thread(_save_turn, request, graph_input, result)
    return _to_response(result, request.session_id)


def _sse(event: str, data: dict[str, Any]) -> str:
    """Formats a line in the Server-Sent Events protocol."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# Replay of the final (approved) text in small chunks for the typing effect.
_REPLAY_CHUNK_SIZE = 6
_REPLAY_DELAY_S = 0.012


async def process_chat_stream(request: ChatRequest) -> AsyncGenerator[str, None]:
    """Executes the graph and streams lifecycle events + ONLY the final text.

    Specialist drafts can be rejected by the quality node, so they are never
    streamed; the final composed answer is replayed in chunks at the end.

    Events emitted:
    - `triage`:     {intents, reasoning}
    - `specialist`: {intent, attempt} when a specialist (re)starts
    - `tool`:       {name, input} when a specialist calls a tool
    - `quality`:    {intent, approved, rejection_reason}
    - `status`:     {phase: "composing"}
    - `token`:      {text} chunks of the final answer
    - `done`:       full ChatResponse
    - `error`:      {detail}
    """
    logger.info(f"Streaming chat: {request.message[:80]}")

    final_state: dict[str, Any] = {}
    attempts: dict[str, int] = {}
    current_intent: str | None = None

    try:
        graph_input = await asyncio.to_thread(_graph_input, request)
        async for event in rethread_agent.astream_events(
            graph_input,
            config={"recursion_limit": envs.recursion_limit},
            version="v2",
        ):
            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chain_end" and name == "triage":
                out = event["data"].get("output") or {}
                yield _sse(
                    "triage",
                    {"intents": out.get("intents"), "reasoning": out.get("reasoning")},
                )

            elif kind == "on_chain_start" and name in INTENT_ORDER:
                current_intent = name
                attempts[name] = attempts.get(name, 0) + 1
                yield _sse("specialist", {"intent": name, "attempt": attempts[name]})

            elif kind == "on_tool_start":
                yield _sse(
                    "tool",
                    {"name": name, "input": event["data"].get("input")},
                )

            elif kind == "on_chain_end" and name == "quality":
                out = event["data"].get("output") or {}
                yield _sse(
                    "quality",
                    {
                        "intent": current_intent,
                        "approved": out.get("quality_approved", False),
                        "rejection_reason": out.get("rejection_reason", ""),
                    },
                )

            elif kind == "on_chain_start" and name == "compose":
                yield _sse("status", {"phase": "composing"})

            elif kind == "on_chain_end" and name == GRAPH_NAME:
                final_state = event["data"].get("output") or {}

        final_text = final_state.get("response", "")
        for i in range(0, len(final_text), _REPLAY_CHUNK_SIZE):
            yield _sse("token", {"text": final_text[i : i + _REPLAY_CHUNK_SIZE]})
            await asyncio.sleep(_REPLAY_DELAY_S)

        await asyncio.to_thread(_save_turn, request, graph_input, final_state)
        yield _sse("done", _to_response(final_state, request.session_id).model_dump())

    except Exception as exc:  # noqa: BLE001
        logger.exception("Error in chat streaming")
        yield _sse("error", {"detail": str(exc)})
