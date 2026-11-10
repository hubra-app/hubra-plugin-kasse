"""kasse_products.item_id: each product is a consumable in Inventory

Revision ID: 3d8f1b6a9c42
Revises: 7e1d4b9a2c58
Create Date: 2026-11-10 13:00:00

"""

from alembic import op
import sqlalchemy as sa

from hubra.core.plugins.ops import columns

revision = "3d8f1b6a9c42"
down_revision = "7e1d4b9a2c58"
branch_labels = None
depends_on = None


def upgrade():
    if "item_id" in columns("kasse_products"):
        return
    with op.batch_alter_table("kasse_products", schema=None) as batch_op:
        # No foreign key: the item is Inventory's, reached through contracts.
        batch_op.add_column(sa.Column("item_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_kasse_products_item_id", ["item_id"])


def downgrade():
    with op.batch_alter_table("kasse_products", schema=None) as batch_op:
        batch_op.drop_index("ix_kasse_products_item_id")
        batch_op.drop_column("item_id")
