import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from ai.tools import handlers


@pytest.fixture
def fake_search(monkeypatch):
    """Replaces the DB search: returns the piece only when no department is given."""
    calls = []

    def search_items(session, query, department=None, **filters):
        calls.append({"department": department, **filters})
        return [] if department else [(SimpleNamespace(), 0.9)]

    @contextmanager
    def session_scope():
        yield None

    monkeypatch.setattr(handlers, "session_scope", session_scope)
    monkeypatch.setattr(handlers.repository, "search_items", search_items)
    monkeypatch.setattr(handlers.repository, "item_to_dict", lambda item: {"sku": "CAL-1"})
    return calls


def test_search_retries_without_inferred_department(fake_search):
    out = handlers.search_catalog.invoke({"query": "calça", "department": "feminino", "brand": "zara"})
    assert json.loads(out) == [{"sku": "CAL-1", "similarity": 0.9}]
    assert [c["department"] for c in fake_search] == ["feminino", None]
    assert all(c["brand"] == "zara" for c in fake_search)  # other filters are kept


def test_search_without_department_runs_once(fake_search):
    handlers.search_catalog.invoke({"query": "calça"})
    assert len(fake_search) == 1
