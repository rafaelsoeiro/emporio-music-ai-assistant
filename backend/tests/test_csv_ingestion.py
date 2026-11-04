import csv
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Category, Customer, Order, OrderItem, Product, Promotion
from app.services.csv_ingestion import CSVIngestionError, ingest_csv_directory


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_datasets(directory: Path, product_name: str = "Test Guitar") -> None:
    # Discovery validates schemas by their headers, independently of file names.
    _write_csv(
        directory / "customers.csv",
        [
            {
                "customer_id": "1",
                "name": "Test Customer",
                "phone": "(67) 99999-9999",
                "email": "customer@example.com",
                "city": "Campo Grande",
            }
        ],
    )
    _write_csv(
        directory / "categories.csv",
        [
            {
                "category_id": "1",
                "name": "Guitars",
                "description": "Electric guitars",
            }
        ],
    )
    _write_csv(
        directory / "products.csv",
        [
            {
                "product_id": "10",
                "price_brl": "999.90",
                "name": product_name,
                "category_id": "1",
                "description": "A product used in tests",
                "stock_quantity": "5",
                "status": "active",
                "specs": '{"color": "black"}',
                "created_at": "2026-01-10",
            }
        ],
    )
    _write_csv(
        directory / "promotions.csv",
        [
            {
                "promotion_id": "100",
                "product_id": "10",
                "discount_percent": "15",
                "description": "Test sale",
                "is_active": "1",
            }
        ],
    )
    _write_csv(
        directory / "orders.csv",
        [
            {
                "order_id": "1000",
                "customer_id": "1",
                "order_date": "2026-01-15",
                "status": "confirmed",
                "total_brl": "1999.80",
                "payment_method": "pix",
                "tracking_code": "",
                "estimated_delivery": "",
                "notes": "",
            }
        ],
    )
    _write_csv(
        directory / "order_items.csv",
        [{"order_id": "1000", "quantity": "2", "product_id": "10"}],
    )


@pytest.fixture
def engine():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


def _row_count(session: Session, model: type[Base]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_ingestion_is_idempotent(engine, tmp_path: Path) -> None:
    _write_datasets(tmp_path)

    with Session(engine) as session:
        first = ingest_csv_directory(session, tmp_path)
    with Session(engine) as session:
        second = ingest_csv_directory(session, tmp_path)
        counts = {
            model.__tablename__: _row_count(session, model)
            for model in (Customer, Category, Product, Promotion, Order, OrderItem)
        }

    assert first.total == 6
    assert second.processed == first.processed
    assert counts == {
        "customers": 1,
        "categories": 1,
        "products": 1,
        "promotions": 1,
        "orders": 1,
        "order_items": 1,
    }


def test_ingestion_updates_existing_rows(engine, tmp_path: Path) -> None:
    _write_datasets(tmp_path)
    with Session(engine) as session:
        ingest_csv_directory(session, tmp_path)

    _write_datasets(tmp_path, product_name="Updated Guitar")
    with Session(engine) as session:
        ingest_csv_directory(session, tmp_path)
    with Session(engine) as session:
        product = session.get(Product, 10)
        assert product is not None
        assert product.name == "Updated Guitar"
        assert product.price_brl == Decimal("999.90")
        assert _row_count(session, Product) == 1


def test_ingestion_maps_optional_order_fields_to_none(engine, tmp_path: Path) -> None:
    _write_datasets(tmp_path)
    with Session(engine) as session:
        ingest_csv_directory(session, tmp_path)
    with Session(engine) as session:
        order = session.get(Order, 1000)
        assert order is not None
        assert order.tracking_code is None
        assert order.estimated_delivery is None
        assert order.notes is None


def test_ingestion_rejects_incomplete_collection(engine, tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "only-customers.csv",
        [
            {
                "customer_id": "1",
                "name": "Test Customer",
                "phone": "123",
                "email": "customer@example.com",
                "city": "Campo Grande",
            }
        ],
    )

    with Session(engine) as session, pytest.raises(
        CSVIngestionError, match="Missing CSV datasets"
    ):
        ingest_csv_directory(session, tmp_path)
