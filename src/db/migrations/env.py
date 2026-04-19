"""
Alembic env.py — configurado para migrations síncronas (padrão Alembic).
Usa psycopg2 para a conexão de migration (não asyncpg).
"""
import sys
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Adiciona raiz do projeto ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from src.db.models import Base  # noqa — importa todos os models
from src.core.config import settings  # noqa

# Configuração básica do Alembic
config = context.config

# Injeta DATABASE_URL_SYNC (psycopg2 — síncrono) no Alembic
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Roda migrations sem conexão (apenas gera SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Roda migrations com conexão síncrona via psycopg2."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
