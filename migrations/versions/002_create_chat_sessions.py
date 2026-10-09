"""create chat sessions (conversation memory)

Revision ID: 002
Revises: 001
Create Date: 2026-10-08

- `chat_sessions`: one row per conversation. The id comes from the backend
  (`session_id` in the chat request). Keeps the piece in context and the
  customer's body measurements, so they don't need to be resent every turn.
- `chat_messages`: the conversation turns (customer message + final answer,
  with the SKUs recommended in it). The last ones are fed back to the agent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("item_id", sa.String(64), nullable=True),
        sa.Column("buyer_measurements", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # "user" (customer) or "assistant" (final answer of the agent)
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Piece in context when the message was sent
        sa.Column("item_id", sa.String(64), nullable=True),
        # Catalog pieces recommended in the answer (assistant only)
        sa.Column("skus", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_chat_messages_session", "chat_messages", ["session_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
