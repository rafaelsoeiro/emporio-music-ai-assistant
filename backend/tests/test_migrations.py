from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_initial_migration_creates_complete_schema(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = _alembic_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    expected_tables = {
        "alembic_version",
        "categories",
        "customers",
        "order_items",
        "orders",
        "products",
        "promotions",
    }
    order_foreign_tables = {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("orders")
    }
    item_foreign_tables = {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("order_items")
    }

    assert set(inspector.get_table_names()) == expected_tables
    assert order_foreign_tables == {"customers"}
    assert item_foreign_tables == {"orders", "products"}

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(
            text(
                """
                INSERT INTO customers
                    (customer_id, name, phone, email, city)
                VALUES
                    (1, 'Customer', '123', 'customer@example.com', 'Test City')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO categories (category_id, name, description)
                VALUES (1, 'Category', 'Test category')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO products
                    (product_id, price_brl, name, category_id, description,
                     stock_quantity, status, specs, created_at)
                VALUES
                    (10, 99.90, 'Product', 1, 'Test product',
                     1, 'active', '{}', '2025-01-01')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO orders
                    (order_id, customer_id, order_date, status, total_brl,
                     payment_method, tracking_code, estimated_delivery, notes)
                VALUES
                    (100, 1, '2025-01-02', 'confirmed', 199.80,
                     'pix', NULL, NULL, NULL)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO order_items (order_id, product_id, quantity)
                VALUES (100, 10, 2)
                """
            )
        )
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()

    assert violations == []
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(database_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
