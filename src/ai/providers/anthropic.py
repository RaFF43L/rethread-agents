"""Provider Anthropic: Claude via API direta (sem embeddings)."""

from langchain_anthropic import ChatAnthropic

from config import envs

from .base import ModelProvider, ProviderRegistry


@ProviderRegistry.register
class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def chat(self, model: str, **kwargs):
        kwargs.setdefault("max_tokens", envs.max_tokens)
        # Sem chave na config, o SDK lê ANTHROPIC_API_KEY do ambiente.
        if envs.anthropic_api_key:
            kwargs.setdefault("api_key", envs.anthropic_api_key)
        return ChatAnthropic(model=model, **kwargs)
