"""Facade agnóstica de modelos.

Cada papel (large / fast / judge) resolve seu próprio provider + modelo a partir
da env. Nenhuma lógica de provider vive aqui — adicionar um provider novo é
criar uma classe em `ai/providers/` e registrá-la.
"""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from ai.providers import ProviderRegistry
from config import envs
from config.logging import get_logger

logger = get_logger(__name__)


class LLMFactory:
    """Facade: um método por papel, provider/modelo vindos da env."""

    @staticmethod
    def _chat(provider: str, model: str, **kwargs) -> BaseChatModel:
        return ProviderRegistry.get(provider).chat(model, **kwargs)

    @staticmethod
    def model_large(**kwargs) -> BaseChatModel:
        """Modelo principal (com tool calling) para os especialistas."""
        return LLMFactory._chat(envs.llm_provider, envs.model, **kwargs)

    @staticmethod
    def model_fast(**kwargs) -> BaseChatModel:
        """Modelo rápido/barato para triagem e composição da resposta."""
        return LLMFactory._chat(
            envs.fast_provider or envs.llm_provider,
            envs.model_fast or envs.model,
            **kwargs,
        )

    @staticmethod
    def model_judge(**kwargs) -> BaseChatModel:
        """Modelo revisor (LLM-as-judge) do loop de qualidade."""
        return LLMFactory._chat(
            envs.judge_provider or envs.llm_provider,
            envs.model_judge or envs.model,
            **kwargs,
        )

    @staticmethod
    def embeddings(**kwargs) -> Embeddings:
        """Embeddings da busca vetorial do catálogo (`EMBED_PROVIDER`)."""
        return ProviderRegistry.get(envs.embed_provider).embeddings(**kwargs)


llm_factory = LLMFactory()
