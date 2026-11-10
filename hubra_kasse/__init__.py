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

from hubra.core.contracts import widget_contract
from hubra.core.modules import Blueprint, Module, NavItem

module = Module(
    code="kasse",
    # Access the standard roles get when a club first switches it on
    # (docs/roles.md in hubra-app/hubra).
    role_defaults={"member": "view", "treasurer": "all"},
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
    # Hubra's features it uses, through contracts (docs/contracts.md in hubra).
    consumes={
        "finance.invoice.create": ">=1,<2",
    },
    # Dashboard widgets (hubra_kasse/widgets.py).
    provides=(
        widget_contract(
            "kasse.tab",
            "hubra_kasse.widgets:tab",
            label="kasse.widget.tab",
            description="kasse.widget.tabHint",
            size="s",
            view="stat",
        ),
        widget_contract(
            "kasse.claims",
            "hubra_kasse.widgets:claims",
            label="kasse.widget.claims",
            description="kasse.widget.claimsHint",
            size="s",
            view="stat",
            perm="kasse.claims.read",
        ),
    ),
)
