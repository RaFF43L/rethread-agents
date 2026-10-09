from typing import Any

from pydantic import BaseModel, Field

from ai.states import Intent
from catalog.schemas import Measurements


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    message: str = Field(
        ...,
        min_length=1,
        description="Customer message",
        examples=["adorei essa calça, ela veste 40 e combina com bota preta?"],
    )
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Conversation id, owned by the backend. Created on first use; the agent "
            "keeps the history, the piece in context and the customer's measurements. "
            "Omit for a one-off message without memory."
        ),
    )
    item_id: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Id or SKU of the piece the customer is looking at. With a session, "
            "omitting it keeps the previous piece in context"
        ),
    )
    buyer_measurements: Measurements | None = Field(
        default=None,
        description=(
            "Customer's BODY measurements in cm, if known. With a session, they are "
            "merged into the ones already stored"
        ),
    )


class AgentOutputOut(BaseModel):
    text: str
    approved: bool
    attempts: int
    skus: list[str] = []


class ChatResponse(BaseModel):
    """Response from the chat endpoint."""

    session_id: str | None = None
    intents: list[Intent]
    reasoning: str
    response: str
    # SKUs of the catalog pieces recommended in `response`, in order of appearance
    # (excludes the piece in context, `item_id`). The text itself has no SKUs.
    skus: list[str] = []
    # Per-specialist answers (quality flags + attempts)
    agent_outputs: dict[str, AgentOutputOut] = {}
    # Global metadata accumulated by nodes
    metadata: dict[str, Any] = {}
