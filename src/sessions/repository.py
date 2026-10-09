"""Chat session data access: get-or-create a session, read history, save a turn."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.logging import get_logger
from sessions.models import ChatMessage, ChatSession

logger = get_logger(__name__)


def open_session(
    session: Session,
    session_id: str,
    item_id: str | None,
    buyer_measurements: dict[str, float],
) -> ChatSession:
    """Gets the session (creating it on first contact) and merges this turn's context.

    A new `item_id` replaces the one in context; measurements are merged (new
    values overwrite, missing keys are kept).
    """
    chat = session.get(ChatSession, session_id)
    if chat is None:
        logger.info(f"New chat session: {session_id}")
        chat = ChatSession(id=session_id, buyer_measurements={})
        session.add(chat)

    if item_id:
        chat.item_id = item_id
    if buyer_measurements:
        chat.buyer_measurements = {**(chat.buyer_measurements or {}), **buyer_measurements}

    session.flush()
    return chat


def recent_messages(session: Session, session_id: str, limit: int) -> list[ChatMessage]:
    """Last `limit` messages of the session, oldest first."""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    return list(reversed(list(session.scalars(stmt))))


def save_turn(
    session: Session,
    session_id: str,
    message: str,
    response: str,
    item_id: str | None,
    skus: list[str],
) -> None:
    """Stores the customer message and the agent's final answer."""
    session.add_all(
        [
            ChatMessage(session_id=session_id, role="user", content=message, item_id=item_id),
            ChatMessage(
                session_id=session_id,
                role="assistant",
                content=response,
                item_id=item_id,
                skus=skus,
            ),
        ]
    )
    session.flush()


def message_to_dict(message: ChatMessage) -> dict[str, Any]:
    """Compact view handed to the graph state."""
    return {"role": message.role, "content": message.content, "skus": list(message.skus or [])}
