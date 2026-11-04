"""Add orders and link order items.

Revision ID: 0002_add_orders
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_orders"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _batch_recreate_mode() -> str:
    """SQLite requires a table copy to add or remove foreign keys."""
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_brl", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column("tracking_code", sa.String(length=50), nullable=True),
        sa.Column("estimated_delivery", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.customer_id"]),
        sa.PrimaryKeyConstraint("order_id"),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"], unique=False)

    with op.batch_alter_table(
        "order_items", recreate=_batch_recreate_mode()
    ) as batch_op:
        batch_op.create_foreign_key(
            "fk_order_items_order_id_orders",
            "orders",
            ["order_id"],
            ["order_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "order_items", recreate=_batch_recreate_mode()
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_order_items_order_id_orders", type_="foreignkey"
        )

    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_table("orders")
