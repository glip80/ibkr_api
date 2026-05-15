"""Alembic migration environment – async-aware."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from ibkr_mcp_service.db.base import Base
from ibkr_mcp_service.db.orm_models import *  # noqa: F401,F403 – register all ORM models

config = context.config

# Override sqlalchemy.url from DATABASE_URL env var if set.
# Convert asyncpg URL to psycopg2 for Alembic's sync driver.
database_url = os.environ.get("DATABASE_URL")
if database_url:
    sync_url = database_url.replace("+asyncpg", "+psycopg2")
    config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()