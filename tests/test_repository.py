from datetime import UTC, datetime
from typing import ClassVar

import pytest
from conftest import FakeSession, size_row

from catalog import repository
from catalog.models import Item
from catalog.schemas import ItemCreate, ItemUpdate


@pytest.mark.parametrize(
    ("value", "expected"),
    [("Calças", "calca"), (" CALÇA ", "calca"), ("calca", "calca"), ("Blusas", "blusa"), ("Vestido", "vestido")],
)
def test_category_key(value, expected):
    assert repository._category_key(value) == expected


def test_unaccent_tables_have_same_length():
    # str.maketrans raises on mismatch, but this documents the SQL `translate` pairing too
    assert len(repository._ACCENTED) == len(repository._PLAIN)


class TestLookupSizeEquivalence:
    ROWS: ClassVar = [
        size_row(1),  # generic
        size_row(2, era="anos 90"),
        size_row(3, brand="Levi's"),
        size_row(4, brand="Levi's", era="anos 90"),
        size_row(5, brand="Zara"),
        size_row(6, department="masculino"),
    ]

    def _lookup(self, rows=None, **kw):
        session = FakeSession(self.ROWS if rows is None else rows)
        row = repository.lookup_size_equivalence(session, category="calça", label_size="40", **kw)
        return row and row.id

    def test_unknown_department_prefers_department_specific_row(self):
        # Current behavior: with department=None, the "masculino" row (6) outranks the
        # generic one (1) by specificity. Change this test if that's not intended.
        assert self._lookup() == 6

    def test_brand_and_era_beat_brand_only(self):
        assert self._lookup(brand="Levi's", era="anos 90") == 4

    def test_brand_only(self):
        assert self._lookup(brand="levi's") == 3

    def test_era_only(self):
        assert self._lookup(era="ANOS 90", department="feminino") == 2

    def test_unknown_brand_falls_back_to_generic(self):
        assert self._lookup(brand="Renner", department="feminino") == 1

    def test_conflicting_department_is_excluded(self):
        assert self._lookup(department="feminino") == 1
        assert self._lookup(department="masculino") == 6

    def test_tie_prefers_newest_row(self):
        assert self._lookup(rows=[size_row(1), size_row(7)]) == 7

    def test_no_candidates(self):
        assert self._lookup(rows=[]) is None
        assert self._lookup(rows=[size_row(1, brand="Zara")]) is None


def _item(**kw) -> Item:
    now = datetime.now(UTC)
    defaults = {
        "id": "id-1", "sku": "CAL-1", "title": "Calça jeans", "category": "calça",
        "size_region": "BR", "status": "active", "style_tags": [], "occasions": [],
        "measurements": {}, "created_at": now, "updated_at": now,
    }
    return Item(**{**defaults, **kw})


@pytest.fixture
def embed_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(repository, "_embed", lambda item: calls.append(item))
    return calls


class TestUpdateItem:
    def test_measurements_are_merged_and_null_removes(self, embed_calls):
        item = _item(measurements={"waist": 80, "hip": 100, "length": 100})
        data = ItemUpdate.model_validate({"measurements": {"waist": None, "hip": 102, "rise": 28}})
        repository.update_item(FakeSession(), item, data)
        assert item.measurements == {"hip": 102, "length": 100, "rise": 28}

    def test_measurement_only_change_does_not_reembed(self, embed_calls):
        repository.update_item(FakeSession(), _item(), ItemUpdate(measurements={"waist": 80}))
        assert embed_calls == []

    def test_non_embed_field_does_not_reembed(self, embed_calls):
        item = _item()
        repository.update_item(FakeSession(), item, ItemUpdate(price=50, status="sold"))
        assert embed_calls == []
        assert item.status == "sold"

    def test_embed_field_reembeds(self, embed_calls):
        item = _item()
        repository.update_item(FakeSession(), item, ItemUpdate(color="azul"))
        assert embed_calls == [item]

    def test_unset_fields_are_untouched(self, embed_calls):
        item = _item(brand="Levi's")
        repository.update_item(FakeSession(), item, ItemUpdate(title="Nova"))
        assert item.brand == "Levi's"


def test_create_item_drops_empty_measurements(embed_calls):
    session = FakeSession()
    session.add = lambda obj: None
    item = repository.create_item(session, ItemCreate(title="x", category="calça", measurements={"waist": 80}))
    assert item.measurements == {"waist": 80}
    assert embed_calls == [item]


def test_embed_failure_does_not_raise(monkeypatch):
    class Broken:
        def embeddings(self):
            raise RuntimeError("provider offline")

    monkeypatch.setattr(repository, "llm_factory", Broken())
    item = _item()
    repository._embed(item)
    assert item.embedding is None


def test_embedding_text_skips_empty_fields():
    text = repository._embedding_text(_item(color="azul", style_tags=["vintage", "boho"]))
    assert text.splitlines() == ["Calça jeans", "categoria: calça", "cor: azul", "estilo: vintage, boho"]


def test_item_to_dict_is_compact():
    data = repository.item_to_dict(_item(measurements={"waist": 80}, price=None))
    assert data["measurements"] == {"waist": 80}
    assert "price" not in data
    assert not {"created_at", "updated_at", "has_embedding"} & data.keys()


def test_item_to_out_has_embedding_flag():
    assert repository.item_to_out(_item(embedding=[0.1, 0.2])).has_embedding is True
    assert repository.item_to_out(_item()).has_embedding is False
