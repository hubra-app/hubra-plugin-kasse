"""Kasse: money between a member and the club outside the membership fee.

- Expense claims (Spesen): a member hands in a receipt photo and the amount,
  the treasurer approves and pays, and the payment is booked as an expense
  with the claim (and its receipt) linked to it.
- The tab (Strichliste): members tick drinks or materials in the app or by
  scanning a QR code at the fridge. The treasurer settles the tab: each
  member's open total becomes an invoice.
- Collective orders: club clothing or merchandise with sizes and a deadline.
  Members order, the board gets one list for the supplier, and each member's
  order becomes an invoice.

Receipts sit in Hubra's file store, encrypted per club.

Permissions:
    kasse.claims.read      see every member's expense claims
    kasse.claims.update    approve, reject and pay them
    kasse.tab.update       manage the products and settle the tab
    kasse.orders.update    run collective orders
"""

from hubra.core.modules import Blueprint, Module, NavItem

module = Module(
    code="kasse",
    name="Kasse",
    description="Expense claims, the drinks tab and collective orders",
    default_enabled=False,
    depends_on=("members", "finance"),
    blueprints=(Blueprint("hubra_kasse.routes", "kasse_bp", "/api/v1/app/kasse"),),
    nav=(
        NavItem(
            "/app/kasse",
            "shell.nav.kasse",
            "receipt",
            section="more",
            order=25,
        ),
    ),
    tables=(
        "kasse_claims",
        "kasse_products",
        "kasse_ticks",
        "kasse_orders",
        "kasse_order_items",
        "kasse_order_lines",
    ),
)
