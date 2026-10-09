"""Alembic environment configuration.

Reads the `DATABASE_URL` from the environment (the same variable that the application uses) and runs
migrations with psycopg (synchronous mode).
"""
import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv, find_dotenv

dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, override=False)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL environment variable is required to run migrations"
        )
    # Ensure psycopg v3 driver (same format used by the application);
    # platforms hand out `postgres://` or `postgresql://`.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def run_migrations_offline() -> None:
    """'Offline' mode — generates SQL without connecting to the database."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """'Online' mode — connects to the database and applies migrations."""
    from sqlalchemy import create_engine, pool

    connectable = create_engine(get_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
