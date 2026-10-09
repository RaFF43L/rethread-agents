from typing import Literal

from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, override=False)


ProviderName = Literal["anthropic", "openai", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        # `FAST_PROVIDER=` in .env means "not set" (falls back to LLM_PROVIDER).
        env_ignore_empty=True,
    )

    # general
    app_name: str = "rethread-agents"
    app_env: Literal["production", "stage", "dev"] = "dev"

    # logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # llm — provider per role (see .env.example)
    llm_provider: ProviderName = "anthropic"
    model: str = "claude-sonnet-5-5"
    # Fast model (triage / compose); provider default = llm_provider
    fast_provider: ProviderName | None = None
    model_fast: str = "claude-haiku-5-5"
    # Judge model (quality review); provider default = llm_provider, model default = model
    judge_provider: ProviderName | None = None
    model_judge: str = ""

    # provider credentials / endpoints (the SDKs also read these from the environment)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # embeddings — Anthropic has no embeddings API
    embed_provider: Literal["openai", "ollama"] = "openai"
    embed_model: str = "text-embedding-3-small"
    # Must match the `items.embedding` column (migration 001)
    embed_dimensions: int = 1536

    # agent behavior
    max_tokens: int = 4096
    # Output token limit for the specialists' final answers
    agent_max_tokens: int = 1200
    # Quality loop cap per specialist
    max_attempts: int = 3
    recursion_limit: int = 50
    search_top_k: int = 5
    # Previous messages of the session fed back to the agent (customer + agent)
    chat_history_messages: int = 10

    # catalog / pgvector (psycopg v3 driver)
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5434/rethread"


envs = Settings()
