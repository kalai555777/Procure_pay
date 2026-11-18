"""Clearbuy's tables, described as classes (the blueprint)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TENANT_FK = "settings.tenants.tenant_id"


class Base(DeclarativeBase):
    """The parent of every table class; holds the list of tables."""


class Tenant(Base):
    """A buying company that uses Clearbuy."""

    __tablename__ = "tenants"
    __table_args__ = {"schema": "settings"}

    tenant_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PurchaseCounter(Base):
    """A tenant's next purchase number."""

    __tablename__ = "purchase_counters"
    __table_args__ = {"schema": "tasks"}

    tenant_id: Mapped[str] = mapped_column(
        String(12), ForeignKey(TENANT_FK, ondelete="RESTRICT"), primary_key=True
    )
    next_number: Mapped[int] = mapped_column(Integer)


class Purchase(Base):
    """One purchase request, such as CB-3105."""

    __tablename__ = "purchases"
    __table_args__ = {"schema": "tasks"}

    tenant_id: Mapped[str] = mapped_column(
        String(12), ForeignKey(TENANT_FK, ondelete="RESTRICT"), primary_key=True
    )
    purchase_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    requester: Mapped[str] = mapped_column(String(64))
    request_details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    stage: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Task(Base):
    """One task, such as CB-3105-T01."""

    __tablename__ = "tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "purchase_number"],
            ["tasks.purchases.tenant_id", "tasks.purchases.purchase_number"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "requester",
            "idempotency_key",
            name="uq_tasks_tenant_requester_key",
        ),
        {"schema": "tasks"},
    )

    tenant_id: Mapped[str] = mapped_column(
        String(12), ForeignKey(TENANT_FK, ondelete="RESTRICT"), primary_key=True
    )
    task_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    purchase_number: Mapped[str | None] = mapped_column(String(20))
    requester: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __mapper_args__ = {"version_id_col": version}
