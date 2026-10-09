"""create catalog schema (items + size equivalences + pgvector)

Revision ID: 001
Revises: None
Create Date: 2026-10-08

- `items`: thrift-store pieces with garment measurements (JSONB, cm) and the
  embedding used by the stylist's semantic search.
- `size_equivalences`: label size -> body measurement ranges, optionally per
  brand / era / department (e.g. "Levi's anos 90, 40 feminino").

The embedding dimension comes from EMBED_DIMENSIONS at migration time
(text-embedding-3-small=1536, nomic-embed-text=768). Changing the embedding
model later requires a new migration + `POST /items/reindex`.
"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from pgvector.sqlalchemy import Vector

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBED_DIMENSIONS = int(os.environ.get("EMBED_DIMENSIONS", "1536"))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sku", sa.String(64), nullable=True, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("department", sa.String(20), nullable=True),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("era", sa.String(30), nullable=True),
        sa.Column("label_size", sa.String(20), nullable=True),
        sa.Column("size_region", sa.String(5), nullable=False, server_default="BR"),
        sa.Column("color", sa.String(60), nullable=True),
        sa.Column("fabric", sa.String(100), nullable=True),
        sa.Column("stretch", sa.String(10), nullable=True),
        sa.Column("style_tags", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("occasions", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("condition", sa.String(60), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("measurements", JSONB(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(EMBED_DIMENSIONS), nullable=True),
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
    op.create_index("ix_items_status_category", "items", ["status", "category"])
    # HNSW index for cosine similarity (stylist semantic search).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_items_embedding_hnsw "
        "ON items USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "size_equivalences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("label_size", sa.String(20), nullable=False),
        sa.Column("region", sa.String(5), nullable=False, server_default="BR"),
        sa.Column("department", sa.String(20), nullable=True),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("era", sa.String(30), nullable=True),
        # {"waist": [76, 80], "hip": [100, 104]} — body measurement ranges in cm
        sa.Column("measurements", JSONB(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_size_equivalences_lookup",
        "size_equivalences",
        ["category", "label_size", "region"],
    )


def downgrade() -> None:
    op.drop_index("ix_size_equivalences_lookup", table_name="size_equivalences")
    op.drop_table("size_equivalences")
    op.execute("DROP INDEX IF EXISTS ix_items_embedding_hnsw")
    op.drop_index("ix_items_status_category", table_name="items")
    op.drop_table("items")
