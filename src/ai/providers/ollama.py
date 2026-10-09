"""Provider Ollama: modelos open source locais (Llama, etc.).

Para os especialistas use um modelo com suporte a tool calling (ex.: llama3.1).
"""

from langchain_ollama import ChatOllama, OllamaEmbeddings

from config import envs

from .base import ModelProvider, ProviderRegistry


@ProviderRegistry.register
class OllamaProvider(ModelProvider):
    name = "ollama"

    def chat(self, model: str, **kwargs):
        # Ollama chama o limite de saída de `num_predict`.
        if "max_tokens" in kwargs:
            kwargs["num_predict"] = kwargs.pop("max_tokens")
        return ChatOllama(model=model, base_url=envs.ollama_base_url, **kwargs)

    def embeddings(self, **kwargs):
        return OllamaEmbeddings(
            model=envs.embed_model,
            base_url=envs.ollama_base_url,
            **kwargs,
        )
