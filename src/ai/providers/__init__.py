"""Providers de modelos. Importar este pacote registra todos os providers."""

from . import anthropic, ollama, openai  # noqa: F401  (auto-registro)
from .base import ModelProvider, ProviderRegistry

__all__ = ["ModelProvider", "ProviderRegistry"]
