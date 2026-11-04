"""SQLAlchemy models exposed for Alembic metadata discovery."""

from app.models.catalog import Category, Product, Promotion
from app.models.customer import Customer
from app.models.order import Order, OrderItem

__all__ = [
    "Category",
    "Customer",
    "Order",
    "OrderItem",
    "Product",
    "Promotion",
]
