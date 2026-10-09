import pytest

from config.envs import Settings, normalize_database_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_normalize_database_url(url, expected):
    assert normalize_database_url(url) == expected


def test_settings_normalizes_database_url():
    assert Settings(database_url="postgres://h/db").database_url == "postgresql+psycopg://h/db"


def test_empty_env_value_falls_back_to_default(monkeypatch):
    # `FAST_PROVIDER=` in .env must mean "not set", not an invalid provider ""
    monkeypatch.setenv("FAST_PROVIDER", "")
    monkeypatch.setenv("MODEL_JUDGE", "")
    settings = Settings()
    assert settings.fast_provider is None
    assert settings.model_judge == ""


def test_invalid_provider_is_rejected():
    with pytest.raises(ValueError):
        Settings(llm_provider="gemini")
