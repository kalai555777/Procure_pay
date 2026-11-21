"""Database connections for Clearbuy: settings, the password, and both pools."""

import os
from dataclasses import dataclass
from typing import Any

from psycopg import Connection
from psycopg.conninfo import make_conninfo
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Dialect, Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry


@dataclass(frozen=True)
class DatabaseSettings:
    """Where the database is and who connects; never the password."""

    host: str
    port: int
    name: str
    user: str


def load_settings() -> DatabaseSettings:
    """Read the database settings from environment variables."""
    return DatabaseSettings(
        host=os.environ["DATABASE_HOST"],
        port=int(os.environ.get("DATABASE_PORT", "5432")),
        name=os.environ["DATABASE_NAME"],
        user=os.environ["DATABASE_USER"],
    )


def get_password() -> str:
    """Return the database password for a new connection.

    Called each time a pool opens a connection. Today it reads an
    environment variable; M1-15 replaces it with the IAM login.
    """
    return os.environ["DATABASE_PASSWORD"]


def create_app_engine(settings: DatabaseSettings) -> Engine:
    """Create SQLAlchemy's engine and pool for Clearbuy's own code."""
    url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.user,
        host=settings.host,
        port=settings.port,
        database=settings.name,
    )
    engine = create_engine(
        url,
        pool_size=5,
        max_overflow=0,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "do_connect")
    def _provide_password(
        dialect: Dialect,
        conn_rec: ConnectionPoolEntry,
        cargs: tuple[Any, ...],
        cparams: dict[str, Any],
    ) -> None:
        """Give each new connection a fresh password."""
        cparams["password"] = get_password()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the factory that hands out SQLAlchemy sessions."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def _checkpoint_connect_kwargs() -> dict[str, Any]:
    """Return the per-connection settings for the checkpoint pool.

    LangGraph's saver needs autocommit, so each checkpoint is saved at once,
    and dict rows, because it reads columns by name.
    """
    return {
        "password": get_password(),
        "autocommit": True,
        "row_factory": dict_row,
    }


def create_checkpoint_pool(
    settings: DatabaseSettings,
) -> ConnectionPool[Connection[DictRow]]:
    """Create psycopg's pool for LangGraph's checkpoint saver."""
    conninfo = make_conninfo(
        host=settings.host,
        port=str(settings.port),
        dbname=settings.name,
        user=settings.user,
        # LangGraph tables live in the tasks schema (Chapter 17.2).
        options="-c search_path=tasks",
    )
    return ConnectionPool(
        conninfo,
        connection_class=Connection[DictRow],
        kwargs=_checkpoint_connect_kwargs,
        min_size=1,
        max_size=4,
        open=False,
    )
