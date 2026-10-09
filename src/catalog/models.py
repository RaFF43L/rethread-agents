"""SQLAlchemy ORM models (schema owned by Alembic — see migrations/versions)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config.envs import envs


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    sku: Mapped[str | None] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    department: Mapped[str | None] = mapped_column(String(20))
    brand: Mapped[str | None] = mapped_column(String(100))
    era: Mapped[str | None] = mapped_column(String(30))
    label_size: Mapped[str | None] = mapped_column(String(20))
    size_region: Mapped[str] = mapped_column(String(5), default="BR")
    color: Mapped[str | None] = mapped_column(String(60))
    fabric: Mapped[str | None] = mapped_column(String(100))
    stretch: Mapped[str | None] = mapped_column(String(10))
    style_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    occasions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    condition: Mapped[str | None] = mapped_column(String(60))
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Garment measurements in cm (see catalog.schemas.Measurements).
    measurements: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(envs.embed_dimensions), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SizeEquivalence(Base):
    __tablename__ = "size_equivalences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50))
    label_size: Mapped[str] = mapped_column(String(20))
    region: Mapped[str] = mapped_column(String(5), default="BR")
    department: Mapped[str | None] = mapped_column(String(20))
    brand: Mapped[str | None] = mapped_column(String(100))
    era: Mapped[str | None] = mapped_column(String(30))
    # Body measurement ranges in cm: {"waist": [74, 78], ...}
    measurements: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
