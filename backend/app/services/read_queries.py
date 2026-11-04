from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Category, Customer, Order, OrderItem, Product, Promotion

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class ProductResult:
    product_id: int
    name: str
    description: str
    price_brl: Decimal
    category_id: int
    category_name: str
    stock_quantity: int


@dataclass(frozen=True)
class PromotionResult:
    promotion_id: int
    description: str
    discount_percent: Decimal
    product_id: int
    product_name: str
    original_price_brl: Decimal
    final_price_brl: Decimal


@dataclass(frozen=True)
class CustomerResult:
    customer_id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True)
class OrderItemResult:
    product_id: int
    product_name: str
    quantity: int
    current_unit_price_brl: Decimal
    current_line_total_brl: Decimal


@dataclass(frozen=True)
class OrderDetailResult:
    order_id: int
    customer: CustomerResult
    items: tuple[OrderItemResult, ...]
    order_date: date
    status: str
    total_brl: Decimal
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _validate_price_range(
    minimum: Decimal | None, maximum: Decimal | None
) -> None:
    if minimum is not None and minimum < 0:
        raise ValueError("minimum price cannot be negative")
    if maximum is not None and maximum < 0:
        raise ValueError("maximum price cannot be negative")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("minimum price cannot be greater than maximum price")


def search_available_products(
    session: Session,
    *,
    term: str | None = None,
    category_id: int | None = None,
    minimum_price: Decimal | None = None,
    maximum_price: Decimal | None = None,
) -> list[ProductResult]:
    """Return active, in-stock products matching the supplied typed filters."""
    _validate_price_range(minimum_price, maximum_price)
    if category_id is not None and category_id <= 0:
        raise ValueError("category_id must be positive")

    statement = (
        select(Product, Category)
        .join(Category, Product.category_id == Category.category_id)
        .where(Product.status == "active", Product.stock_quantity > 0)
        .order_by(Product.name, Product.product_id)
    )

    normalized_term = term.strip() if term else ""
    if normalized_term:
        pattern = f"%{_escape_like(normalized_term)}%"
        statement = statement.where(
            or_(
                Product.name.ilike(pattern, escape="\\"),
                Product.description.ilike(pattern, escape="\\"),
            )
        )
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if minimum_price is not None:
        statement = statement.where(Product.price_brl >= minimum_price)
    if maximum_price is not None:
        statement = statement.where(Product.price_brl <= maximum_price)

    with session.no_autoflush:
        rows = session.execute(statement).all()

    return [
        ProductResult(
            product_id=product.product_id,
            name=product.name,
            description=product.description,
            price_brl=product.price_brl,
            category_id=category.category_id,
            category_name=category.name,
            stock_quantity=product.stock_quantity,
        )
        for product, category in rows
    ]


def get_active_promotions(session: Session) -> list[PromotionResult]:
    """Return active promotions and their calculated final product prices."""
    statement = (
        select(Promotion, Product)
        .join(Product, Promotion.product_id == Product.product_id)
        .where(Promotion.is_active.is_(True))
        .order_by(Promotion.promotion_id)
    )

    with session.no_autoflush:
        rows = session.execute(statement).all()

    results = []
    for promotion, product in rows:
        multiplier = (Decimal("100") - promotion.discount_percent) / Decimal(
            "100"
        )
        final_price = (product.price_brl * multiplier).quantize(
            _CENT, rounding=ROUND_HALF_UP
        )
        results.append(
            PromotionResult(
                promotion_id=promotion.promotion_id,
                description=promotion.description,
                discount_percent=promotion.discount_percent,
                product_id=product.product_id,
                product_name=product.name,
                original_price_brl=product.price_brl,
                final_price_brl=final_price,
            )
        )
    return results


def get_order_detail(session: Session, order_id: int) -> OrderDetailResult | None:
    """Return an order with customer and items, or ``None`` when it does not exist."""
    header_statement = (
        select(Order, Customer)
        .join(Customer, Order.customer_id == Customer.customer_id)
        .where(Order.order_id == order_id)
    )
    items_statement = (
        select(OrderItem, Product)
        .join(Product, OrderItem.product_id == Product.product_id)
        .where(OrderItem.order_id == order_id)
        .order_by(Product.name, Product.product_id)
    )

    with session.no_autoflush:
        header = session.execute(header_statement).one_or_none()
        if header is None:
            return None
        item_rows = session.execute(items_statement).all()

    order, customer = header
    items = tuple(
        OrderItemResult(
            product_id=product.product_id,
            product_name=product.name,
            quantity=item.quantity,
            current_unit_price_brl=product.price_brl,
            current_line_total_brl=(product.price_brl * item.quantity).quantize(
                _CENT
            ),
        )
        for item, product in item_rows
    )
    return OrderDetailResult(
        order_id=order.order_id,
        customer=CustomerResult(
            customer_id=customer.customer_id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            city=customer.city,
        ),
        items=items,
        order_date=order.order_date,
        status=order.status,
        total_brl=order.total_brl,
        payment_method=order.payment_method,
        tracking_code=order.tracking_code,
        estimated_delivery=order.estimated_delivery,
        notes=order.notes,
    )
