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


def _seed_revision_0001(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO customers
                    (customer_id, name, phone, email, city)
                VALUES
                    (1, 'Legacy Customer', '123', 'legacy@example.com', 'Test City')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO categories (category_id, name, description)
                VALUES (1, 'Legacy Category', 'Existing data')
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
                    (10, 99.90, 'Legacy Product', 1, 'Existing data',
                     1, 'active', '{}', '2025-01-01')
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
    engine.dispose()


def test_add_orders_migration_preserves_existing_order_items(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = _alembic_config(database_url)

    command.upgrade(config, "0001_initial")
    _seed_revision_0001(database_url)
    command.upgrade(config, "0002_add_orders")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    foreign_tables = {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("order_items")
    }

    with engine.begin() as connection:
        item = connection.execute(
            text(
                """
                SELECT order_id, product_id, quantity
                FROM order_items
                """
            )
        ).one()
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

    with engine.connect() as connection:
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()

    assert tuple(item) == (100, 10, 2)
    assert foreign_tables == {"orders", "products"}
    assert violations == []
    engine.dispose()

    command.downgrade(config, "0001_initial")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    with engine.connect() as connection:
        preserved_item = connection.execute(
            text("SELECT order_id, product_id, quantity FROM order_items")
        ).one()

    assert "orders" not in inspector.get_table_names()
    assert tuple(preserved_item) == (100, 10, 2)
    engine.dispose()
