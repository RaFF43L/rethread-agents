"""Tools the specialists call (LangChain `@tool`). They return JSON strings.

- Stylist:     get_item_spec, search_catalog
- Fit & Sizing: get_item_spec, lookup_size_equivalence, compare_fit
"""

import json
from typing import Any

from langchain_core.tools import tool

from catalog import repository
from catalog.db import session_scope
from catalog.fit import compare_fit as compute_fit
from catalog.schemas import Measurements
from config.logging import get_logger

logger = get_logger(__name__)


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@tool
def get_item_spec(item_ref: str) -> str:
    """Returns the technical sheet of a catalog piece, by id or SKU: garment
    measurements in cm (circumferences are the full round), fabric stretch,
    label size, brand, era, color, fabric, style tags, occasions and status."""
    logger.info(f"Tool get_item_spec({item_ref})")
    with session_scope() as session:
        item = repository.get_item(session, item_ref)
        if item is None:
            return _json({"error": f"Peça '{item_ref}' não encontrada no acervo."})
        return _json(repository.item_to_dict(item))


@tool
def search_catalog(
    query: str,
    category: str | None = None,
    department: str | None = None,
    exclude_item: str | None = None,
    max_price: float | None = None,
    k: int = 5,
) -> str:
    """Semantic search over the ACTIVE (available) pieces of the thrift store.

    Args:
        query: free description of style, color, fabric and occasion,
            e.g. "blusa de seda clara para trabalho, estilo minimalista".
        category: optional category filter (calça, camisa, vestido, saia,
            jaqueta, blusa, short...); accents, case and plural don't matter.
        department: optional: feminino, masculino or unissex. Use ONLY when the
            customer said it explicitly; never infer it (it hides other pieces).
        exclude_item: optional id/SKU to leave out (the piece being discussed).
        max_price: optional price cap in BRL when the customer gives a budget
            (e.g. "até 30 reais" -> 30).
        k: how many pieces to return (1-10).
    """
    logger.info(
        f"Tool search_catalog({query!r}, category={category}, "
        f"department={department}, max_price={max_price})"
    )
    with session_scope() as session:
        hits = repository.search_items(
            session,
            query,
            k=max(1, min(k, 10)),
            category=category,
            department=department,
            exclude=exclude_item,
            max_price=max_price,
        )
        return _json(
            [{**repository.item_to_dict(item), "similarity": sim} for item, sim in hits]
        )


@tool
def lookup_size_equivalence(
    category: str,
    label_size: str,
    brand: str | None = None,
    era: str | None = None,
    department: str | None = None,
    region: str = "BR",
) -> str:
    """Converts a label size (e.g. "40", "M") into BODY measurement ranges in cm,
    using the store's equivalence table. Uses the most specific row available
    (brand + era > brand > era > generic table).

    Args:
        category: piece category (calça, camisa, vestido...).
        label_size: the size printed on the label or the size the customer wears.
        brand: optional brand, to use brand-specific sizing.
        era: optional era (e.g. "anos 90"), since old sizing differs from today's.
        department: optional: feminino, masculino or unissex.
        region: sizing system, default BR.
    """
    logger.info(f"Tool lookup_size_equivalence({category}, {label_size}, {brand}, {era})")
    with session_scope() as session:
        row = repository.lookup_size_equivalence(
            session,
            category=category,
            label_size=label_size,
            region=region,
            department=department,
            brand=brand,
            era=era,
        )
        if row is None:
            return _json(
                {"error": f"Sem equivalência cadastrada para {category} tamanho {label_size} ({region})."}
            )
        return _json(
            {
                "category": row.category,
                "label_size": row.label_size,
                "region": row.region,
                "department": row.department,
                "brand": row.brand or "genérica",
                "era": row.era or "qualquer",
                "body_measurement_ranges_cm": row.measurements,
                "notes": row.notes,
            }
        )


@tool
def compare_fit(item_ref: str, body: Measurements) -> str:
    """Compares the piece's garment measurements with the customer's BODY
    measurements (cm) and returns, per dimension, the ease and a verdict
    (apertado / justo / confortável / folgado, sobra/falta for lengths),
    already accounting for the fabric stretch.

    Args:
        item_ref: piece id or SKU.
        body: customer's body measurements in cm (only the ones you know).
    """
    body_dict = (
        body.model_dump(exclude_none=True)
        if isinstance(body, Measurements)
        else {k: v for k, v in dict(body).items() if v is not None}
    )
    logger.info(f"Tool compare_fit({item_ref}, {body_dict})")
    with session_scope() as session:
        item = repository.get_item(session, item_ref)
        if item is None:
            return _json({"error": f"Peça '{item_ref}' não encontrada no acervo."})
        result = compute_fit(item.measurements or {}, body_dict, stretch=item.stretch)
        return _json({"item": item.title, "label_size": item.label_size, **result})


STYLIST_TOOLS = [get_item_spec, search_catalog]
FIT_TOOLS = [get_item_spec, lookup_size_equivalence, compare_fit]
