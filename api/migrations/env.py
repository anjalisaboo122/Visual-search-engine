"""
Alembic runs this file every time you run an alembic command.
Its job: connect to the database and run the migration scripts.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from api.app.config import get_settings
from api.app.db import Base
from api.app import models  # noqa: F401  (import registers the tables on Base)

config = context.config

# Use the [logger_*] sections of alembic.ini, so you see "Running upgrade ..." lines.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Lets `alembic revision --autogenerate` compare models.py to the real DB.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Print the SQL instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to Postgres and apply the migrations."""
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
