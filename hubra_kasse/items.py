"""Each Strichliste product is a consumable in Inventory.

Inventory holds what the club has, and counts the stock; the Kasse keeps
what only the tab needs (price, order on the list, on the tab or not). The
two stay in line through Inventory's contracts, never its code or tables,
and everything here works without Inventory too (the product then just
has no item):

- a product added or renamed here goes to its item with
  ``inventory.items.save`` (``push``), stock fields given in the product
  form go along;
- a tick takes from the stock, a tick taken back puts it back
  (``inventory.stock.adjust``, ``take``);
- an item renamed in Inventory renames the product, a deleted one takes the
  product off the tab (``on_item_saved``, ``on_item_deleted``);
- products from before (or made while Inventory was off) get their item from
  the job ``kasse-link-items`` (``link_missing``).
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from hubra.core.contracts import SYSTEM, ActionUnavailable, Refused, available, call, query
from hubra.core.extensions import db

from .models import KasseProduct

log = logging.getLogger(__name__)

TYPE = "Consumable"
# Stock fields the product form passes on to the item.
STOCK_FIELDS = ("stock", "min_stock", "unit")


def push(product: KasseProduct, actor_id: int | None = None, **stock) -> None:
    """Make or update the product's item, in the caller's transaction.
    ``stock`` holds stock fields to set (stock, min_stock, unit)."""
    if not available("inventory.stock.adjust"):
        # Inventory is off, or too old to count stock: the job links it later.
        return
    fields = {"name": product.name, **{k: v for k, v in stock.items() if k in STOCK_FIELDS}}
    try:
        if product.item_id is not None:
            try:
                call(
                    "inventory.items.save",
                    item_id=product.item_id,
                    actor_id=actor_id,
                    actor=SYSTEM,
                    **fields,
                )
                return
            except Refused as exc:
                if exc.code != "NOT_FOUND":
                    raise
                product.item_id = None  # deleted under us: make a new one
        fields.setdefault("stock", 0)
        item = call(
            "inventory.items.save",
            category=TYPE,
            status="available",
            actor_id=actor_id,
            actor=SYSTEM,
            **fields,
        )
    except ActionUnavailable:
        # Inventory is off or not installed; the job links it later.
        log.info("kasse: inventory unavailable, product %s not linked", product.id)
        return
    product.item_id = item["id"]
    db.session.flush()


def take(product_id: int | None, qty: int, member_id, actor_id, back: bool = False) -> None:
    """A tick took *qty* from the stock (``back``: a tick taken back)."""
    if product_id is None:
        return
    product = db.session.get(KasseProduct, product_id)
    if product is None or product.item_id is None:
        return
    try:
        call(
            "inventory.stock.adjust",
            item_id=product.item_id,
            delta=qty if back else -qty,
            reason="Strichliste",
            member_id=member_id,
            actor_id=actor_id,
            actor=SYSTEM,
        )
    except (ActionUnavailable, Refused) as exc:
        # The tick counts either way; the stock is a count, not a gate.
        log.info("kasse: stock of item %s not changed: %s", product.item_id, exc)


def stock_of(products: list[KasseProduct]) -> dict[int, dict]:
    """The items of these products, by item id (empty without Inventory)."""
    ids = [p.item_id for p in products if p.item_id is not None]
    if not ids or not available("inventory.items.get"):
        return {}
    try:
        return {i["id"]: i for i in query("inventory.items.get", ids=ids, actor=SYSTEM)}
    except ActionUnavailable:
        return {}


def _product_for(item_id: int) -> KasseProduct | None:
    return db.session.scalar(select(KasseProduct).where(KasseProduct.item_id == item_id))


def on_item_saved(tenant_id=None, item_id: int = 0, name: str | None = None, **_) -> None:
    """An item was changed in Inventory: a product's item renames it."""
    product = _product_for(item_id)
    if product is None:
        return
    found = query("inventory.items.get", ids=[item_id], actor=SYSTEM)
    if found and found[0]["name"][:120] != product.name:
        product.name = found[0]["name"][:120]
        db.session.flush()


def on_item_deleted(tenant_id=None, item_id: int = 0, **_) -> None:
    """A product's item was deleted in Inventory: the product leaves the tab
    (ticks keep their name and price)."""
    product = _product_for(item_id)
    if product is None:
        return
    product.item_id = None
    product.active = False
    db.session.flush()


def link_missing(limit: int = 200) -> int:
    """Give products on the tab without an item one. Returns how many got one."""
    if not available("inventory.stock.adjust"):
        return 0
    rows = db.session.scalars(
        select(KasseProduct)
        .where(KasseProduct.item_id.is_(None))
        .where(KasseProduct.active.is_(True))
        .order_by(KasseProduct.id)
        .limit(limit)
    ).all()
    done = 0
    for product in rows:
        push(product)
        if product.item_id is not None:
            done += 1
    return done
