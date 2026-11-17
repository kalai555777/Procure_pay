"""Tests that the migrations build Clearbuy's tables from an empty database."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from procure_pay import db

EXPECTED_TABLES = {
    "settings.tenants",
    "tasks.purchase_counters",
    "tasks.purchases",
    "tasks.tasks",
}


def _clearbuy_tables() -> set[str]:
    engine = db.create_app_engine(db.load_settings())
    try:
        inspector = inspect(engine)
        schemas = set(inspector.get_schema_names())
        return {
            f"{schema}.{table}"
            for schema in ("settings", "tasks")
            if schema in schemas
            for table in inspector.get_table_names(schema=schema)
        }
    finally:
        engine.dispose()


def test_migrations_run_from_an_empty_database(
    empty_database: str, alembic_cfg: Config
) -> None:
    command.upgrade(alembic_cfg, "head")
    assert _clearbuy_tables() == EXPECTED_TABLES
    command.downgrade(alembic_cfg, "base")
    assert _clearbuy_tables() == set()
    command.upgrade(alembic_cfg, "head")
    assert _clearbuy_tables() == EXPECTED_TABLES
