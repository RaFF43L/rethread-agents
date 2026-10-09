"""Catalog business logic (items + size equivalences) — transport agnostic."""

from catalog import repository
from catalog.db import session_scope
from catalog.schemas import (
    ItemCreate,
    ItemOut,
    ItemSearchHit,
    ItemSearchRequest,
    ItemUpdate,
    SizeEquivalenceIn,
    SizeEquivalenceOut,
)
from config.logging import get_logger

logger = get_logger(__name__)


class NotFoundError(LookupError):
    pass


def create_item(data: ItemCreate) -> ItemOut:
    with session_scope() as session:
        return repository.item_to_out(repository.create_item(session, data))


def get_item(ref: str) -> ItemOut:
    with session_scope() as session:
        item = repository.get_item(session, ref)
        if item is None:
            raise NotFoundError(f"Item '{ref}' not found")
        return repository.item_to_out(item)


def update_item(ref: str, data: ItemUpdate) -> ItemOut:
    with session_scope() as session:
        item = repository.get_item(session, ref)
        if item is None:
            raise NotFoundError(f"Item '{ref}' not found")
        return repository.item_to_out(repository.update_item(session, item, data))


def list_items(
    status: str | None = None, category: str | None = None, limit: int = 100
) -> list[ItemOut]:
    with session_scope() as session:
        items = repository.list_items(session, status=status, category=category, limit=limit)
        return [repository.item_to_out(i) for i in items]


def reindex_items(only_missing: bool = True) -> int:
    with session_scope() as session:
        return repository.reindex_items(session, only_missing=only_missing)


def search_items(request: ItemSearchRequest) -> list[ItemSearchHit]:
    with session_scope() as session:
        hits = repository.search_items(
            session,
            request.query,
            k=request.k,
            category=request.category,
            department=request.department,
            max_price=request.max_price,
        )
        return [
            ItemSearchHit(item=repository.item_to_out(item), similarity=sim)
            for item, sim in hits
        ]


def create_size_equivalence(data: SizeEquivalenceIn) -> SizeEquivalenceOut:
    with session_scope() as session:
        row = repository.create_size_equivalence(session, data)
        return SizeEquivalenceOut.model_validate(row)


def list_size_equivalences(category: str | None = None) -> list[SizeEquivalenceOut]:
    with session_scope() as session:
        rows = repository.list_size_equivalences(session, category=category)
        return [SizeEquivalenceOut.model_validate(r) for r in rows]
