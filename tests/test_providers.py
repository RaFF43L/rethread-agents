import pytest

from ai import llm
from ai.providers import ProviderRegistry


def test_all_providers_registered():
    assert ProviderRegistry.available() == ["anthropic", "ollama", "openai"]


def test_unknown_provider():
    with pytest.raises(ValueError, match="Provider desconhecido"):
        ProviderRegistry.get("gemini")


def test_anthropic_has_no_embeddings():
    with pytest.raises(NotImplementedError):
        ProviderRegistry.get("anthropic").embeddings()


def test_get_returns_singleton():
    assert ProviderRegistry.get("ollama") is ProviderRegistry.get("ollama")


@pytest.fixture
def chat_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(llm.LLMFactory, "_chat", staticmethod(lambda p, m, **kw: calls.append((p, m))))
    return calls


def test_fast_and_judge_fall_back_to_main_provider(monkeypatch, chat_calls):
    for key, value in {
        "llm_provider": "openai", "model": "gpt-big", "fast_provider": None,
        "model_fast": "gpt-mini", "judge_provider": None, "model_judge": "",
    }.items():
        monkeypatch.setattr(llm.envs, key, value)

    llm.LLMFactory.model_fast()
    llm.LLMFactory.model_judge()
    assert chat_calls == [("openai", "gpt-mini"), ("openai", "gpt-big")]


def test_role_providers_override(monkeypatch, chat_calls):
    for key, value in {
        "llm_provider": "anthropic", "fast_provider": "ollama", "model_fast": "llama3.1",
        "judge_provider": "openai", "model_judge": "gpt-judge",
    }.items():
        monkeypatch.setattr(llm.envs, key, value)

    llm.LLMFactory.model_fast()
    llm.LLMFactory.model_judge()
    assert chat_calls == [("ollama", "llama3.1"), ("openai", "gpt-judge")]
