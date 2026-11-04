"""Create the initial store schema.

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("category_id"),
    )
    op.create_table(
        "customers",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("customer_id"),
    )
    op.create_index("ix_customers_email", "customers", ["email"], unique=False)
    op.create_table(
        "products",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("price_brl", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("specs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.category_id"]),
        sa.PrimaryKeyConstraint("product_id"),
    )
    op.create_index(
        "ix_products_category_id", "products", ["category_id"], unique=False
    )
    op.create_table(
        "order_items",
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
        sa.PrimaryKeyConstraint("order_id", "product_id"),
    )
    op.create_table(
        "promotions",
        sa.Column("promotion_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
        sa.PrimaryKeyConstraint("promotion_id"),
    )
    op.create_index(
        "ix_promotions_product_id", "promotions", ["product_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_promotions_product_id", table_name="promotions")
    op.drop_table("promotions")
    op.drop_table("order_items")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_customers_email", table_name="customers")
    op.drop_table("customers")
    op.drop_table("categories")
