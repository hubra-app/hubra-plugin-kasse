"""kasse claims, products, ticks, orders, order items and order lines

Runs in public and in every club's schema, tracked in its own version table
(alembic_version_kasse). has_table() keeps it safe to run twice.

Revision ID: 7e1d4b9a2c58
Revises:
Create Date: 2026-11-05 11:00:00

"""

from alembic import op
import sqlalchemy as sa

from hubra.core.plugins.ops import has_table

revision = "7e1d4b9a2c58"
down_revision = None
branch_labels = None
depends_on = None


def _ts(name, nullable=True):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _member(name):
    return sa.Column(name, sa.Integer(), nullable=True)


def _member_fk(name):
    return sa.ForeignKeyConstraint([name], ["members.id"], ondelete="SET NULL")


def _invoice_fk(name="invoice_id"):
    return sa.ForeignKeyConstraint([name], ["invoices.id"], ondelete="SET NULL")


def upgrade():
    if not has_table("kasse_claims"):
        op.create_table(
            "kasse_claims",
            sa.Column("id", sa.Integer(), nullable=False),
            _member("member_id"),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("spent_on", sa.Date(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("iban", sa.String(34), nullable=True),
            sa.Column("receipt_key", sa.String(120), nullable=True),
            sa.Column("receipt_name", sa.String(200), nullable=True),
            sa.Column("receipt_type", sa.String(100), nullable=True),
            sa.Column("status", sa.String(12), nullable=False),
            _member("decided_by"),
            _ts("decided_at"),
            sa.Column("decision_note", sa.String(500), nullable=True),
            sa.Column("transaction_id", sa.Integer(), nullable=True),
            _ts("paid_at"),
            _ts("created_at", nullable=False),
            _member_fk("member_id"),
            _member_fk("decided_by"),
            sa.ForeignKeyConstraint(
                ["transaction_id"], ["transactions.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_kasse_claims_member_id", "kasse_claims", ["member_id"])

    if not has_table("kasse_products"):
        op.create_table(
            "kasse_products",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not has_table("kasse_ticks"):
        op.create_table(
            "kasse_ticks",
            sa.Column("id", sa.Integer(), nullable=False),
            _member("member_id"),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.Column("qty", sa.Integer(), nullable=False),
            _member("created_by"),
            _ts("created_at", nullable=False),
            sa.Column("invoice_id", sa.Integer(), nullable=True),
            _ts("settled_at"),
            _member_fk("member_id"),
            _member_fk("created_by"),
            sa.ForeignKeyConstraint(
                ["product_id"], ["kasse_products.id"], ondelete="SET NULL"
            ),
            _invoice_fk(),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_kasse_ticks_member_id", "kasse_ticks", ["member_id"])
        op.create_index("ix_kasse_ticks_invoice_id", "kasse_ticks", ["invoice_id"])

    if not has_table("kasse_orders"):
        op.create_table(
            "kasse_orders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("deadline", sa.Date(), nullable=False),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("supplier", sa.String(200), nullable=True),
            _member("created_by"),
            _ts("created_at", nullable=False),
            _ts("billed_at"),
            _member_fk("created_by"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not has_table("kasse_order_items"):
        op.create_table(
            "kasse_order_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.Column("sizes", sa.String(300), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["order_id"], ["kasse_orders.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_kasse_order_items_order_id", "kasse_order_items", ["order_id"]
        )

    if not has_table("kasse_order_lines"):
        op.create_table(
            "kasse_order_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            _member("member_id"),
            sa.Column("size", sa.String(40), nullable=True),
            sa.Column("qty", sa.Integer(), nullable=False),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.Column("invoice_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(
                ["order_id"], ["kasse_orders.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["item_id"], ["kasse_order_items.id"], ondelete="CASCADE"
            ),
            _member_fk("member_id"),
            _invoice_fk(),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_kasse_order_lines_order_id", "kasse_order_lines", ["order_id"]
        )
        op.create_index(
            "ix_kasse_order_lines_item_id", "kasse_order_lines", ["item_id"]
        )
        op.create_index(
            "ix_kasse_order_lines_member_id", "kasse_order_lines", ["member_id"]
        )


def downgrade():
    for table in (
        "kasse_order_lines",
        "kasse_order_items",
        "kasse_orders",
        "kasse_ticks",
        "kasse_products",
        "kasse_claims",
    ):
        if has_table(table):
            op.drop_table(table)
