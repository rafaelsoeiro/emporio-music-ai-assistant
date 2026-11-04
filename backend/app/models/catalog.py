from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Category(Base):
    __tablename__ = "categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.category_id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    specs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[date] = mapped_column(Date, nullable=False)


class Promotion(Base):
    __tablename__ = "promotions"

    promotion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id"), nullable=False, index=True
    )
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
