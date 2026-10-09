"""Shared fakes. No test touches Postgres or a real LLM provider."""

from types import SimpleNamespace

import pytest


class FakeModel:
    """Stands in for a chat model: `with_structured_output(...).invoke` and
    plain `invoke` return the canned `result` and record the calls."""

    def __init__(self, result):
        self.result = result
        self.calls: list = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.result


class FakeLLMFactory:
    def __init__(self, fast=None, judge=None, large=None):
        self.fast, self.judge, self.large = fast, judge, large

    def model_fast(self, **kwargs):
        return self.fast

    def model_judge(self, **kwargs):
        return self.judge

    def model_large(self, **kwargs):
        return self.large


@pytest.fixture
def fake_llm(monkeypatch):
    """Patches `ai.agent.llm_factory`; returns a builder for the canned models."""
    import ai.agent

    def install(**models):
        factory = FakeLLMFactory(**models)
        monkeypatch.setattr(ai.agent, "llm_factory", factory)
        return factory

    return install


class FakeSession:
    """Minimal SQLAlchemy Session double for repository functions."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.flushed = 0

    def scalars(self, stmt):
        return iter(self.rows)

    def flush(self):
        self.flushed += 1


def size_row(id, brand=None, era=None, department=None, **kw):
    return SimpleNamespace(id=id, brand=brand, era=era, department=department, **kw)
