"""Provider OpenAI-compatível: chat + embeddings via API.

`OPENAI_BASE_URL` (opcional) aponta para qualquer endpoint compatível: vLLM,
LM Studio, OpenRouter... A chave vem de `OPENAI_API_KEY`.
"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from config import envs

from .base import ModelProvider, ProviderRegistry


def _client_kwargs() -> dict:
    kwargs: dict = {}
    if envs.openai_base_url:
        kwargs["base_url"] = envs.openai_base_url
    if envs.openai_api_key:
        kwargs["api_key"] = envs.openai_api_key
    return kwargs


@ProviderRegistry.register
class OpenAIProvider(ModelProvider):
    name = "openai"

    def chat(self, model: str, **kwargs):
        return ChatOpenAI(model=model, **_client_kwargs(), **kwargs)

    def embeddings(self, **kwargs):
        return OpenAIEmbeddings(
            model=envs.embed_model,
            dimensions=envs.embed_dimensions,
            **_client_kwargs(),
            **kwargs,
        )
