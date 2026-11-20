"""Tests that the migrations build Clearbuy's tables from an empty database."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from procure_pay import db

EXPECTED_TABLES = {
    "settings.tenants",
    "tasks.checkpoint_blobs",
    "tasks.checkpoint_migrations",
    "tasks.checkpoint_writes",
    "tasks.checkpoints",
    "tasks.claims",
    "tasks.purchase_counters",
    "tasks.purchases",
    "tasks.tasks",
}
HEAD = "47ea77b4ef4c"


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


def _public_tables() -> list[str]:
    engine = db.create_app_engine(db.load_settings())
    try:
        return inspect(engine).get_table_names(schema="public")
    finally:
        engine.dispose()


def test_migrations_run_from_an_empty_database(
    empty_database: str, alembic_cfg: Config
) -> None:
    command.upgrade(alembic_cfg, "head")
    assert _clearbuy_tables() == EXPECTED_TABLES
    assert _public_tables() == []
    command.downgrade(alembic_cfg, "base")
    assert _clearbuy_tables() == set()
    command.upgrade(alembic_cfg, "head")
    assert _clearbuy_tables() == EXPECTED_TABLES
    engine = db.create_app_engine(db.load_settings())
    try:
        version = (
            engine.connect()
            .execute(text("SELECT version_num FROM migrations.alembic_version"))
            .scalar_one()
        )
    finally:
        engine.dispose()
    assert version == HEAD


def test_autogenerate_finds_no_changes(
    empty_database: str, alembic_cfg: Config
) -> None:
    command.upgrade(alembic_cfg, "head")
    command.check(alembic_cfg)
