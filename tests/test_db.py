"""Tests for the database connection module."""

import pytest
from sqlalchemy import text

from procure_pay import db


def test_load_settings_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_HOST", "example-host")
    monkeypatch.setenv("DATABASE_PORT", "6543")
    monkeypatch.setenv("DATABASE_NAME", "example-db")
    monkeypatch.setenv("DATABASE_USER", "example-user")
    assert db.load_settings() == db.DatabaseSettings(
        host="example-host", port=6543, name="example-db", user="example-user"
    )


def test_get_password_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_PASSWORD", "not-a-real-password")
    assert db.get_password() == "not-a-real-password"


def test_app_engine_connects() -> None:
    engine = db.create_app_engine(db.load_settings())
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_session_factory_gives_sessions() -> None:
    engine = db.create_app_engine(db.load_settings())
    try:
        session_factory = db.create_session_factory(engine)
        with session_factory() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_checkpoint_pool_gives_langgraph_settings() -> None:
    pool = db.create_checkpoint_pool(db.load_settings())
    pool.open(wait=True, timeout=10)
    try:
        with pool.connection() as conn:
            assert conn.autocommit is True
            row = conn.execute("SELECT 1 AS answer").fetchone()
            assert row == {"answer": 1}
            path = conn.execute("SHOW search_path").fetchone()
            assert path == {"search_path": "tasks"}
    finally:
        pool.close()
