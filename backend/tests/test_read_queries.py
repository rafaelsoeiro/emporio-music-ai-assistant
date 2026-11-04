from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Category, Customer, Order, OrderItem, Product, Promotion
from app.services.read_queries import (
    get_active_promotions,
    get_order_detail,
    search_available_products,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        _seed(database_session)
        yield database_session
    engine.dispose()


def _product(
    product_id: int,
    name: str,
    category_id: int,
    price: str,
    *,
    status: str = "active",
    stock: int = 5,
) -> Product:
    return Product(
        product_id=product_id,
        name=name,
        category_id=category_id,
        price_brl=Decimal(price),
        description=f"Description for {name}",
        stock_quantity=stock,
        status=status,
        specs={},
        created_at=date(2025, 1, 1),
    )


def _seed(session: Session) -> None:
    session.add_all(
        [
            Category(category_id=1, name="Guitars", description="Guitars"),
            Category(category_id=2, name="Keyboards", description="Keyboards"),
            _product(10, "Electric Guitar", 1, "999.90"),
            _product(11, "Acoustic Guitar", 1, "799.90", stock=0),
            _product(12, "Vintage Guitar", 1, "1299.90", status="discontinued"),
            _product(20, "Stage Keyboard", 2, "2500.00"),
            Customer(
                customer_id=1,
                name="Test Customer",
                phone="123",
                email="customer@example.com",
                city="Campo Grande",
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            Promotion(
                promotion_id=1,
                product_id=10,
                discount_percent=Decimal("10"),
                description="Active sale",
                is_active=True,
            ),
            Promotion(
                promotion_id=2,
                product_id=20,
                discount_percent=Decimal("20"),
                description="Inactive sale",
                is_active=False,
            ),
            Order(
                order_id=100,
                customer_id=1,
                order_date=date(2026, 2, 1),
                status="shipped",
                total_brl=Decimal("1999.80"),
                payment_method="pix",
                tracking_code="BR123",
                estimated_delivery=date(2026, 2, 8),
                notes="Leave at reception",
            ),
        ]
    )
    session.flush()
    session.add(OrderItem(order_id=100, product_id=10, quantity=2))
    session.commit()


def test_search_products_combines_all_filters(session: Session) -> None:
    results = search_available_products(
        session,
        term="guitar",
        category_id=1,
        minimum_price=Decimal("900"),
        maximum_price=Decimal("1100"),
    )

    assert [result.product_id for result in results] == [10]
    assert results[0].category_name == "Guitars"
    assert results[0].stock_quantity == 5


def test_search_products_excludes_unavailable_and_returns_empty(
    session: Session,
) -> None:
    assert search_available_products(session, term="Acoustic") == []
    assert search_available_products(session, term="Vintage") == []
    assert search_available_products(session, term="%") == []
    assert search_available_products(session, term="' OR 1=1 --") == []
    assert search_available_products(session, term="missing") == []


def test_search_products_rejects_invalid_filters(session: Session) -> None:
    with pytest.raises(ValueError, match="minimum price"):
        search_available_products(
            session,
            minimum_price=Decimal("100"),
            maximum_price=Decimal("50"),
        )


def test_active_promotions_include_final_price(session: Session) -> None:
    results = get_active_promotions(session)

    assert len(results) == 1
    assert results[0].promotion_id == 1
    assert results[0].original_price_brl == Decimal("999.90")
    assert results[0].final_price_brl == Decimal("899.91")


def test_order_detail_contains_customer_items_and_delivery(session: Session) -> None:
    result = get_order_detail(session, 100)

    assert result is not None
    assert result.customer.name == "Test Customer"
    assert result.status == "shipped"
    assert result.payment_method == "pix"
    assert result.tracking_code == "BR123"
    assert result.estimated_delivery == date(2026, 2, 8)
    assert result.items[0].product_id == 10
    assert result.items[0].quantity == 2
    assert result.items[0].current_line_total_brl == Decimal("1999.80")


def test_missing_order_returns_none(session: Session) -> None:
    assert get_order_detail(session, 999) is None


def test_services_only_issue_select_statements(session: Session) -> None:
    statements: list[str] = []

    def record_statement(
        connection, cursor, statement, parameters, context, executemany
    ) -> None:
        statements.append(statement.strip().upper())

    event.listen(session.bind, "before_cursor_execute", record_statement)
    search_available_products(session, term="guitar")
    get_active_promotions(session)
    get_order_detail(session, 100)
    event.remove(session.bind, "before_cursor_execute", record_statement)

    assert statements
    assert all(statement.startswith("SELECT") for statement in statements)
