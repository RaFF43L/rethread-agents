"""Abstração de providers de modelos (chat + embeddings).

`ModelProvider` é a interface agnóstica: o resto do código depende dela, não de
implementações concretas. `ProviderRegistry` mapeia nome -> classe; cada provider
se auto-registra com o decorator `@ProviderRegistry.register`.

Diferente do agent-task-triage, o provider é escolhido POR PAPEL (especialista,
rápido, juiz) via env — dá para rodar a triagem num Llama local e os
especialistas no Claude, por exemplo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel


class ModelProvider(ABC):
    """Interface de um provider de modelos."""

    name: str

    @abstractmethod
    def chat(self, model: str, **kwargs) -> BaseChatModel:
        """Constrói o chat model `model` deste provider."""

    def embeddings(self, **kwargs) -> Embeddings:
        """Modelo de embeddings (busca vetorial do catálogo)."""
        raise NotImplementedError(
            f"Provider {self.name!r} não oferece embeddings. "
            "Use EMBED_PROVIDER=openai ou EMBED_PROVIDER=ollama."
        )


class ProviderRegistry:
    """Registro de providers por nome. Novo provider = nova classe registrada."""

    _providers: ClassVar[dict[str, type[ModelProvider]]] = {}
    _instances: ClassVar[dict[str, ModelProvider]] = {}

    @classmethod
    def register(cls, provider_cls: type[ModelProvider]) -> type[ModelProvider]:
        """Decorator: registra a classe sob `provider_cls.name`."""
        cls._providers[provider_cls.name] = provider_cls
        return provider_cls

    @classmethod
    def get(cls, name: str) -> ModelProvider:
        """Retorna a instância (singleton) do provider pelo nome."""
        try:
            return cls._instances.setdefault(name, cls._providers[name]())
        except KeyError:
            raise ValueError(
                f"Provider desconhecido: {name!r}. Disponíveis: {sorted(cls._providers)}"
            ) from None

    @classmethod
    def available(cls) -> list[str]:
        return sorted(cls._providers)
