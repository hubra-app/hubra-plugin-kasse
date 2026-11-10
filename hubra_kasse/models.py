"""The Kasse tables (one copy per club schema)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from hubra.core.extensions import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _member_fk() -> ForeignKey:
    return ForeignKey("members.id", ondelete="SET NULL")


def _invoice_fk() -> ForeignKey:
    return ForeignKey("invoices.id", ondelete="SET NULL")


# Claim status: submitted → approved → paid, or rejected.
CLAIM_STATES = ("submitted", "approved", "rejected", "paid")


class KasseClaim(db.Model):
    """An expense a member paid for the club and wants back."""

    __tablename__ = "kasse_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int | None] = mapped_column(Integer, _member_fk(), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    spent_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    # Where to pay it; empty: the IBAN on the member's profile, or cash.
    iban: Mapped[str | None] = mapped_column(String(34))
    receipt_key: Mapped[str | None] = mapped_column(String(120))
    receipt_name: Mapped[str | None] = mapped_column(String(200))
    receipt_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(12), default="submitted", nullable=False)
    decided_by: Mapped[int | None] = mapped_column(Integer, _member_fk())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(500))
    transaction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class KasseProduct(db.Model):
    """Something on the tab: a drink, a snack, material by the piece."""

    __tablename__ = "kasse_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Its consumable in Inventory, which counts the stock (hubra_kasse.items).
    # No foreign key: Inventory's table is reached only through contracts.
    item_id: Mapped[int | None] = mapped_column(Integer, index=True)


class KasseTick(db.Model):
    """One tick on a member's tab, at the price of the day."""

    __tablename__ = "kasse_ticks"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int | None] = mapped_column(Integer, _member_fk(), index=True)
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("kasse_products.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, _member_fk())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    # Set once the tab is settled; the tick is then on that invoice.
    invoice_id: Mapped[int | None] = mapped_column(Integer, _invoice_fk(), index=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Order status: open → closed → billed.
ORDER_STATES = ("open", "closed", "billed")


class KasseOrder(db.Model):
    """A collective order: club clothing, merchandise, a bulk purchase."""

    __tablename__ = "kasse_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[int | None] = mapped_column(Integer, _member_fk())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    billed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KasseOrderItem(db.Model):
    __tablename__ = "kasse_order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kasse_orders.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Comma separated, e.g. "S, M, L, XL"; empty: one size.
    sizes: Mapped[str | None] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class KasseOrderLine(db.Model):
    """What one member ordered of one item in one size."""

    __tablename__ = "kasse_order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kasse_orders.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kasse_order_items.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[int | None] = mapped_column(Integer, _member_fk(), index=True)
    size: Mapped[str | None] = mapped_column(String(40))
    qty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(Integer, _invoice_fk())
