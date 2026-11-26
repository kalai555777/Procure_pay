"""Grant each role its rights.

Each part's role gets its own schema only (Chapter 17.4, AD-215), plus one
temporary exception until M1-22. Runs as clearbuy_owner, which owns every
schema and table; the roles themselves come from procure_pay.setup_database.

Revision ID: f0be2caa233c
Revises: 47ea77b4ef4c
Create Date: 2026-11-26 01:00:54.318350

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0be2caa233c"
down_revision: str | Sequence[str] | None = "47ea77b4ef4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = (
    # clearbuy_tasks: the tasks schema (L3 and L4).
    "GRANT USAGE ON SCHEMA tasks TO clearbuy_tasks",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA tasks"
    " TO clearbuy_tasks",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA tasks TO clearbuy_tasks",
    "ALTER DEFAULT PRIVILEGES FOR ROLE clearbuy_owner IN SCHEMA tasks"
    " GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO clearbuy_tasks",
    "ALTER DEFAULT PRIVILEGES FOR ROLE clearbuy_owner IN SCHEMA tasks"
    " GRANT USAGE, SELECT ON SEQUENCES TO clearbuy_tasks",
    # clearbuy_settings: the settings schema (L2, with L4 and L7).
    "GRANT USAGE ON SCHEMA settings TO clearbuy_settings",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA settings"
    " TO clearbuy_settings",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA settings TO clearbuy_settings",
    "ALTER DEFAULT PRIVILEGES FOR ROLE clearbuy_owner IN SCHEMA settings"
    " GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO clearbuy_settings",
    "ALTER DEFAULT PRIVILEGES FOR ROLE clearbuy_owner IN SCHEMA settings"
    " GRANT USAGE, SELECT ON SEQUENCES TO clearbuy_settings",
    # The one exception until M1-22: the api's tenant lookup by name.
    "GRANT USAGE ON SCHEMA settings TO clearbuy_tasks",
    "GRANT SELECT ON settings.tenants TO clearbuy_tasks",
)

REVOKES = (
    # The reverse of GRANTS, last first.
    "REVOKE SELECT ON settings.tenants FROM clearbuy_tasks",
    "REVOKE USAGE ON SCHEMA settings FROM clearbuy_tasks",
    "ALTER DEFAULT PRIVILEGES FOR ROLE clearbuy_owner IN SCHEMA settings"
    " REVOKE USAGE, SELECT ON SEQUENCES FROM clearbuy_settings",
    "ALTER DEFAULT PRIVILEGES FOR ROLE clearbuy_owner IN SCHEMA settings"
    " REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM clearbuy_settings",
    "REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA settings FROM clearbuy_settings",
    "REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA settings"
    " FROM clearbuy_settings",
    "REVOKE USAGE ON SCHEMA settings FROM clearbuy_settings",
    "ALTER DEFAULT PRIVILEGES FOR ROLE clearbuy_owner IN SCHEMA tasks"
    " REVOKE USAGE, SELECT ON SEQUENCES FROM clearbuy_tasks",
    "ALTER DEFAULT PRIVILEGES FOR ROLE clearbuy_owner IN SCHEMA tasks"
    " REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM clearbuy_tasks",
    "REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA tasks FROM clearbuy_tasks",
    "REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA tasks"
    " FROM clearbuy_tasks",
    "REVOKE USAGE ON SCHEMA tasks FROM clearbuy_tasks",
)


def upgrade() -> None:
    """Grant each part's role its own schema, plus the one exception."""
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    """Revoke every right upgrade() granted (laptop and CI only)."""
    for statement in REVOKES:
        op.execute(statement)
