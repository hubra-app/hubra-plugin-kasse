"""Links the database doesn't keep for us.

Club schemas are cloned from public with ``LIKE ... INCLUDING ALL``, which
copies no foreign keys, so the ``ondelete`` on Kasse's columns never runs
in a real club. Hubra applies the member links itself when a member is
deleted; the rest is done here:

- an invoice deleted (``invoice.deleted``): its ticks go back on the open
  tab and its order lines are unbilled again, as ``SET NULL`` intended;
- an order or a product deleted: the routes delete its items and lines, or
  unlink its ticks, themselves;
- ``purge_orphans`` (daily job) catches what slipped past: links to invoices,
  transactions, products and orders that are gone.
"""

from __future__ import annotations

from sqlalchemy import delete, exists, select, update

from hubra.core.extensions import db
from hubra.core.models.finance import Invoice, Transaction

from .models import (
    KasseClaim,
    KasseOrder,
    KasseOrderItem,
    KasseOrderLine,
    KasseProduct,
    KasseTick,
)


def _unbill(invoice_ids) -> int:
    ticks = db.session.execute(
        update(KasseTick)
        .where(KasseTick.invoice_id.in_(invoice_ids))
        .values(invoice_id=None, settled_at=None)
    ).rowcount
    lines = db.session.execute(
        update(KasseOrderLine)
        .where(KasseOrderLine.invoice_id.in_(invoice_ids))
        .values(invoice_id=None)
    ).rowcount
    return (ticks or 0) + (lines or 0)


def on_invoice_deleted(tenant_id=None, invoice_id: int | None = None, **_) -> None:
    """An invoice is gone: what was on it is open again."""
    if invoice_id is not None:
        _unbill([invoice_id])


def delete_order_rows(order_id: int) -> None:
    """An order's lines and items (no CASCADE in a club schema)."""
    db.session.execute(delete(KasseOrderLine).where(KasseOrderLine.order_id == order_id))
    db.session.execute(delete(KasseOrderItem).where(KasseOrderItem.order_id == order_id))


def unlink_product(product_id: int) -> None:
    """A product is gone: its ticks keep their name and price."""
    db.session.execute(
        update(KasseTick).where(KasseTick.product_id == product_id).values(product_id=None)
    )


def purge_orphans() -> dict:
    """Links to rows that are gone, as their ``ondelete`` would have done."""
    gone_invoice = ~exists().where(Invoice.id == KasseTick.invoice_id)
    invoice_ids = set(
        db.session.scalars(
            select(KasseTick.invoice_id).where(KasseTick.invoice_id.isnot(None), gone_invoice)
        )
    )
    invoice_ids |= set(
        db.session.scalars(
            select(KasseOrderLine.invoice_id).where(
                KasseOrderLine.invoice_id.isnot(None),
                ~exists().where(Invoice.id == KasseOrderLine.invoice_id),
            )
        )
    )
    reopened = _unbill(list(invoice_ids)) if invoice_ids else 0
    transactions = db.session.execute(
        update(KasseClaim)
        .where(
            KasseClaim.transaction_id.isnot(None),
            ~exists().where(Transaction.id == KasseClaim.transaction_id),
        )
        .values(transaction_id=None)
    ).rowcount
    products = db.session.execute(
        update(KasseTick)
        .where(
            KasseTick.product_id.isnot(None),
            ~exists().where(KasseProduct.id == KasseTick.product_id),
        )
        .values(product_id=None)
    ).rowcount
    lines = db.session.execute(
        delete(KasseOrderLine).where(~exists().where(KasseOrder.id == KasseOrderLine.order_id))
    ).rowcount
    items = db.session.execute(
        delete(KasseOrderItem).where(~exists().where(KasseOrder.id == KasseOrderItem.order_id))
    ).rowcount
    return {
        "reopened": reopened,
        "transactions": transactions or 0,
        "products": products or 0,
        "orderRows": (lines or 0) + (items or 0),
    }
