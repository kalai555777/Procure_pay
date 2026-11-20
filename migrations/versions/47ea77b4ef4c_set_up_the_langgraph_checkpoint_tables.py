"""Set up the LangGraph checkpoint tables.

Revision ID: 47ea77b4ef4c
Revises: 62d314b8698b
Create Date: 2026-11-20 09:24:24.341935

"""

from collections.abc import Sequence

from alembic import op
from langgraph.checkpoint.postgres import PostgresSaver

from procure_pay import db

# revision identifiers, used by Alembic.
revision: str = "47ea77b4ef4c"
down_revision: str | Sequence[str] | None = "62d314b8698b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LANGGRAPH_TABLES = (
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
    "checkpoint_migrations",
)


def upgrade() -> None:
    """Run LangGraph's own setup, which creates its tables in the tasks schema."""
    pool = db.create_checkpoint_pool(db.load_settings())
    pool.open(wait=True, timeout=10)
    try:
        PostgresSaver(pool).setup()
    finally:
        pool.close()


def downgrade() -> None:
    """Drop LangGraph's tables (laptop and CI only; AWS restores a backup)."""
    for table in LANGGRAPH_TABLES:
        op.drop_table(table, schema="tasks")
