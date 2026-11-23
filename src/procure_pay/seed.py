"""Seed the test tenants and their purchase counters (local, ci, and test only).

Run with ``python -m procure_pay.seed``. Safe to rerun: it adds only what
is missing and never changes an existing counter. It refuses to run unless
``APP_ENV`` is one of ``SEED_ENVIRONMENTS``.
"""

import os
import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session

from procure_pay import db
from procure_pay.fixed_identity import FIXED_TENANT_NAME
from procure_pay.models import PurchaseCounter, Tenant

SEED_TENANTS = {FIXED_TENANT_NAME: 3105, "Test Co.": 2001}
SEED_ENVIRONMENTS = ("local", "ci", "test")
_ID_ALPHABET = string.ascii_lowercase + string.digits


class SeedError(Exception):
    """The seed cannot run safely."""


def new_tenant_id() -> str:
    """Return a new random tenant ID: "t-" and 10 lowercase letters and digits."""
    return "t-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(10))


def seed(session: Session) -> dict[str, str]:
    """Add each seed tenant and its counter if missing; return name to tenant ID."""
    seeded: dict[str, str] = {}
    for name, first_number in SEED_TENANTS.items():
        matches = session.scalars(select(Tenant).where(Tenant.name == name)).all()
        if len(matches) > 1:
            raise SeedError(f"More than one tenant is named {name!r}")
        if matches:
            tenant = matches[0]
        else:
            tenant = Tenant(tenant_id=new_tenant_id(), name=name)
            session.add(tenant)
            session.flush()
        if session.get(PurchaseCounter, tenant.tenant_id) is None:
            session.add(
                PurchaseCounter(tenant_id=tenant.tenant_id, next_number=first_number)
            )
        seeded[name] = tenant.tenant_id
    session.commit()
    return seeded


def main() -> None:
    """Run the seed against the configured database, only in an allowed APP_ENV."""
    app_env = os.environ.get("APP_ENV")
    if app_env not in SEED_ENVIRONMENTS:
        allowed = ", ".join(SEED_ENVIRONMENTS)
        raise SeedError(f"The seed runs only when APP_ENV is one of: {allowed}")
    engine = db.create_app_engine(db.load_settings())
    try:
        with db.create_session_factory(engine)() as session:
            for name, tenant_id in seed(session).items():
                print(f"{name}: {tenant_id}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
