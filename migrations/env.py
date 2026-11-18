"""Alembic's environment: connects through procure_pay.db and builds the schemas."""

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import text

from procure_pay import db
from procure_pay.models import Base

VERSION_SCHEMA = "migrations"
OWNED_SCHEMAS = {"tasks", "settings"}

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def include_name(name: str | None, type_: str, parent_names: Any) -> bool:
    """Compare only Clearbuy's own schemas when drafting a migration."""
    if type_ == "schema":
        return name in OWNED_SCHEMAS
    return True


def run_migrations_online() -> None:
    """Run the migrations against the database, through db.py's engine."""
    engine = db.create_app_engine(db.load_settings())
    try:
        with engine.connect() as connection:
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS migrations"))
            connection.commit()
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                include_schemas=True,
                include_name=include_name,
                version_table_schema=VERSION_SCHEMA,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Clearbuy runs migrations online only: alembic upgrade head")
run_migrations_online()
