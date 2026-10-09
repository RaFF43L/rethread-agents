"""Catalog data access: items CRUD, semantic search and size equivalences.

Embeddings live in `items.embedding` (not in a separate langchain collection),
so the search always filters on the CURRENT `status` — a sold piece never
shows up for the stylist.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.llm import llm_factory
from catalog.models import Item, SizeEquivalence
from catalog.schemas import ItemCreate, ItemOut, ItemUpdate, SizeEquivalenceIn
from config.envs import envs
from config.logging import get_logger

logger = get_logger(__name__)

_ACCENTED = "áàâãäéèêëíìîïóòôõöúùûüç"
_PLAIN = "aaaaaeeeeiiiiooooouuuuc"
_UNACCENT = str.maketrans(_ACCENTED, _PLAIN)


def _category_key(value: str) -> str:
    """Category as compared: lowercase, no accents, no plural "s" ("Calças" -> "calca")."""
    return value.strip().lower().translate(_UNACCENT).rstrip("s")


def _category_matches(column, value: str):
    """SQL predicate equivalent to `_category_key(column) == _category_key(value)`."""
    normalized = func.rtrim(func.translate(func.lower(func.trim(column)), _ACCENTED, _PLAIN), "s")
    return normalized == _category_key(value)


# Fields that feed the embedding text; changing any of them re-embeds the item.
EMBED_FIELDS = {
    "title",
    "description",
    "category",
    "department",
    "brand",
    "era",
    "color",
    "fabric",
    "style_tags",
    "occasions",
}


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def item_to_out(item: Item) -> ItemOut:
    return ItemOut.model_validate(
        {
            **{c: getattr(item, c) for c in ItemOut.model_fields if hasattr(item, c)},
            "measurements": item.measurements or {},
            "has_embedding": item.embedding is not None,
        }
    )


def item_to_dict(item: Item) -> dict[str, Any]:
    """Compact JSON-friendly view used by the agents' tools."""
    data = item_to_out(item).model_dump(
        exclude={"created_at", "updated_at", "has_embedding"}, exclude_none=True
    )
    data["measurements"] = {k: v for k, v in data.get("measurements", {}).items() if v is not None}
    return data


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
def _embedding_text(item: Item) -> str:
    parts = [
        item.title,
        f"categoria: {item.category}",
        f"departamento: {item.department}" if item.department else "",
        f"marca: {item.brand}" if item.brand else "",
        f"época: {item.era}" if item.era else "",
        f"cor: {item.color}" if item.color else "",
        f"tecido: {item.fabric}" if item.fabric else "",
        f"estilo: {', '.join(item.style_tags)}" if item.style_tags else "",
        f"ocasiões: {', '.join(item.occasions)}" if item.occasions else "",
        item.description or "",
    ]
    return "\n".join(p for p in parts if p)


def _embed(item: Item) -> None:
    """Embeds the item. A provider failure must not block catalog edits:
    the item is saved without embedding and can be fixed via reindex."""
    try:
        item.embedding = llm_factory.embeddings().embed_query(_embedding_text(item))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Embedding failed for item '{item.title}': {exc}")


# --------------------------------------------------------------------------- #
# Items
# --------------------------------------------------------------------------- #
def get_item(session: Session, ref: str) -> Item | None:
    """Finds an item by id or SKU."""
    item = session.get(Item, ref)
    if item is None:
        item = session.scalar(select(Item).where(Item.sku == ref))
    return item


def create_item(session: Session, data: ItemCreate) -> Item:
    payload = data.model_dump(exclude={"measurements"})
    item = Item(**payload, measurements=data.measurements.model_dump(exclude_none=True))
    _embed(item)
    session.add(item)
    session.flush()
    return item


def update_item(session: Session, item: Item, data: ItemUpdate) -> Item:
    changes = data.model_dump(exclude_unset=True)
    measurements = changes.pop("measurements", None)

    for field, value in changes.items():
        setattr(item, field, value)

    if measurements is not None:
        # Merge: new values overwrite, null removes, missing keys are kept.
        merged = {**(item.measurements or {}), **measurements}
        item.measurements = {k: v for k, v in merged.items() if v is not None}

    if changes.keys() & EMBED_FIELDS:
        _embed(item)

    session.flush()
    return item


def list_items(
    session: Session,
    status: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[Item]:
    stmt = select(Item).order_by(Item.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Item.status == status)
    if category:
        stmt = stmt.where(_category_matches(Item.category, category))
    return list(session.scalars(stmt))


def reindex_items(session: Session, only_missing: bool = True) -> int:
    """(Re)generates embeddings. Returns how many items were embedded."""
    stmt = select(Item)
    if only_missing:
        stmt = stmt.where(Item.embedding.is_(None))
    count = 0
    for item in session.scalars(stmt):
        _embed(item)
        count += item.embedding is not None
    session.flush()
    return count


def search_items(
    session: Session,
    query: str,
    k: int | None = None,
    category: str | None = None,
    department: str | None = None,
    exclude: str | None = None,
    max_price: float | None = None,
) -> list[tuple[Item, float]]:
    """Cosine-similarity search over ACTIVE items. Returns (item, similarity 0-1)."""
    query_vector = llm_factory.embeddings().embed_query(query)
    distance = Item.embedding.cosine_distance(query_vector)

    stmt = (
        select(Item, distance.label("distance"))
        .where(Item.status == "active", Item.embedding.is_not(None))
        .order_by(distance)
        .limit(k or envs.search_top_k)
    )
    if category:
        stmt = stmt.where(_category_matches(Item.category, category))
    if department:
        stmt = stmt.where(Item.department.in_([department, "unissex"]))
    if exclude:
        stmt = stmt.where(Item.id != exclude, func.coalesce(Item.sku, "") != exclude)
    if max_price is not None:
        stmt = stmt.where(Item.price <= max_price)

    return [(item, round(1 - float(dist), 4)) for item, dist in session.execute(stmt)]


# --------------------------------------------------------------------------- #
# Size equivalences
# --------------------------------------------------------------------------- #
def create_size_equivalence(session: Session, data: SizeEquivalenceIn) -> SizeEquivalence:
    payload = data.model_dump()
    payload["measurements"] = {k: list(v) for k, v in data.measurements.items()}
    row = SizeEquivalence(**payload)
    session.add(row)
    session.flush()
    return row


def list_size_equivalences(
    session: Session, category: str | None = None
) -> list[SizeEquivalence]:
    stmt = select(SizeEquivalence).order_by(
        SizeEquivalence.category, SizeEquivalence.label_size
    )
    if category:
        stmt = stmt.where(_category_matches(SizeEquivalence.category, category))
    return list(session.scalars(stmt))


def lookup_size_equivalence(
    session: Session,
    category: str,
    label_size: str,
    region: str = "BR",
    department: str | None = None,
    brand: str | None = None,
    era: str | None = None,
) -> SizeEquivalence | None:
    """Most specific row for the label size: brand+era > brand > era > generic.

    Rows with a brand/era that differs from the request are excluded; rows where
    those fields are empty act as wildcards. An unknown department (None) does
    not exclude rows — only a conflicting one does.
    """
    stmt = select(SizeEquivalence).where(
        _category_matches(SizeEquivalence.category, category),
        func.lower(SizeEquivalence.label_size) == label_size.lower(),
        func.upper(SizeEquivalence.region) == region.upper(),
    )
    candidates = list(session.scalars(stmt))

    def matches(value: str | None, wanted: str | None) -> bool:
        return value is None or (wanted is not None and value.lower() == wanted.lower())

    def score(row: SizeEquivalence) -> tuple[int, int]:
        specificity = (
            (4 if row.brand else 0) + (2 if row.era else 0) + (1 if row.department else 0)
        )
        return specificity, row.id

    eligible = [
        r
        for r in candidates
        if matches(r.brand, brand)
        and matches(r.era, era)
        and (department is None or matches(r.department, department))
    ]
    return max(eligible, key=score, default=None)
