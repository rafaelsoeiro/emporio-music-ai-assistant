import csv
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Session

from app.models import Category, Customer, Order, OrderItem, Product, Promotion

Row = dict[str, Any]
Parser = Callable[[Mapping[str, str]], Row]


class CSVIngestionError(ValueError):
    """Raised when the CSV collection is incomplete or malformed."""


@dataclass(frozen=True)
class Dataset:
    name: str
    model: type[DeclarativeBase]
    headers: frozenset[str]
    parser: Parser


@dataclass(frozen=True)
class IngestionResult:
    processed: Mapping[str, int]

    @property
    def total(self) -> int:
        return sum(self.processed.values())


def _integer(value: str, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CSVIngestionError(f"Invalid integer in {field}: {value!r}") from exc


def _decimal(value: str, field: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise CSVIngestionError(f"Invalid decimal in {field}: {value!r}") from exc


def _boolean(value: str, field: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise CSVIngestionError(f"Invalid boolean in {field}: {value!r}")


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CSVIngestionError(f"Invalid date in {field}: {value!r}") from exc


def _optional_date(value: str, field: str) -> date | None:
    return _date(value, field) if value.strip() else None


def _optional_text(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _customer(row: Mapping[str, str]) -> Row:
    return {
        "customer_id": _integer(row["customer_id"], "customer_id"),
        "name": row["name"].strip(),
        "phone": row["phone"].strip(),
        "email": row["email"].strip(),
        "city": row["city"].strip(),
    }


def _category(row: Mapping[str, str]) -> Row:
    return {
        "category_id": _integer(row["category_id"], "category_id"),
        "name": row["name"].strip(),
        "description": row["description"].strip(),
    }


def _product(row: Mapping[str, str]) -> Row:
    try:
        specs = json.loads(row["specs"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise CSVIngestionError(f"Invalid product specs: {exc}") from exc
    if not isinstance(specs, dict):
        raise CSVIngestionError("Product specs must be a JSON object")

    return {
        "product_id": _integer(row["product_id"], "product_id"),
        "price_brl": _decimal(row["price_brl"], "price_brl"),
        "name": row["name"].strip(),
        "category_id": _integer(row["category_id"], "category_id"),
        "description": row["description"].strip(),
        "stock_quantity": _integer(row["stock_quantity"], "stock_quantity"),
        "status": row["status"].strip(),
        "specs": specs,
        "created_at": _date(row["created_at"], "created_at"),
    }


def _promotion(row: Mapping[str, str]) -> Row:
    return {
        "promotion_id": _integer(row["promotion_id"], "promotion_id"),
        "product_id": _integer(row["product_id"], "product_id"),
        "discount_percent": _decimal(
            row["discount_percent"], "discount_percent"
        ),
        "description": row["description"].strip(),
        "is_active": _boolean(row["is_active"], "is_active"),
    }


def _order_item(row: Mapping[str, str]) -> Row:
    return {
        "order_id": _integer(row["order_id"], "order_id"),
        "product_id": _integer(row["product_id"], "product_id"),
        "quantity": _integer(row["quantity"], "quantity"),
    }


def _order(row: Mapping[str, str]) -> Row:
    return {
        "order_id": _integer(row["order_id"], "order_id"),
        "customer_id": _integer(row["customer_id"], "customer_id"),
        "order_date": _date(row["order_date"], "order_date"),
        "status": row["status"].strip(),
        "total_brl": _decimal(row["total_brl"], "total_brl"),
        "payment_method": row["payment_method"].strip(),
        "tracking_code": _optional_text(row["tracking_code"]),
        "estimated_delivery": _optional_date(
            row["estimated_delivery"], "estimated_delivery"
        ),
        "notes": _optional_text(row["notes"]),
    }


DATASETS = (
    Dataset(
        "customers",
        Customer,
        frozenset({"customer_id", "name", "phone", "email", "city"}),
        _customer,
    ),
    Dataset(
        "categories",
        Category,
        frozenset({"category_id", "name", "description"}),
        _category,
    ),
    Dataset(
        "products",
        Product,
        frozenset(
            {
                "product_id",
                "price_brl",
                "name",
                "category_id",
                "description",
                "stock_quantity",
                "status",
                "specs",
                "created_at",
            }
        ),
        _product,
    ),
    Dataset(
        "promotions",
        Promotion,
        frozenset(
            {
                "promotion_id",
                "product_id",
                "discount_percent",
                "description",
                "is_active",
            }
        ),
        _promotion,
    ),
    Dataset(
        "orders",
        Order,
        frozenset(
            {
                "order_id",
                "customer_id",
                "order_date",
                "status",
                "total_brl",
                "payment_method",
                "tracking_code",
                "estimated_delivery",
                "notes",
            }
        ),
        _order,
    ),
    Dataset(
        "order_items",
        OrderItem,
        frozenset({"order_id", "quantity", "product_id"}),
        _order_item,
    ),
)


def _discover_files(directory: Path) -> dict[str, Path]:
    discovered: dict[str, Path] = {}
    datasets_by_headers = {dataset.headers: dataset for dataset in DATASETS}

    for path in sorted(directory.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            headers = frozenset(csv.DictReader(stream).fieldnames or ())
        dataset = datasets_by_headers.get(headers)
        if dataset is None:
            raise CSVIngestionError(f"Unknown CSV schema in {path.name}")
        if dataset.name in discovered:
            raise CSVIngestionError(f"Duplicate CSV dataset: {dataset.name}")
        discovered[dataset.name] = path

    missing = [dataset.name for dataset in DATASETS if dataset.name not in discovered]
    if missing:
        raise CSVIngestionError(f"Missing CSV datasets: {', '.join(missing)}")
    return discovered


def _read_rows(path: Path, dataset: Dataset) -> list[Row]:
    parsed: list[Row] = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for line_number, row in enumerate(csv.DictReader(stream), start=2):
            try:
                parsed.append(dataset.parser(row))
            except (CSVIngestionError, KeyError) as exc:
                raise CSVIngestionError(
                    f"{path.name}:{line_number}: {exc}"
                ) from exc
    return parsed


def _upsert(session: Session, dataset: Dataset, rows: list[Row]) -> None:
    if not rows:
        return

    table = dataset.model.__table__
    statement = sqlite_insert(table).values(rows)
    primary_keys = [column.name for column in table.primary_key.columns]
    primary_key_names = set(primary_keys)
    updates = {
        column.name: getattr(statement.excluded, column.name)
        for column in table.columns
        if column.name not in primary_key_names
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=primary_keys,
            set_=updates,
        )
    )


def ingest_csv_directory(session: Session, directory: Path) -> IngestionResult:
    if not directory.is_dir():
        raise CSVIngestionError(f"CSV directory does not exist: {directory}")

    discovered = _discover_files(directory)
    processed: dict[str, int] = {}

    with session.begin():
        for dataset in DATASETS:
            rows = _read_rows(discovered[dataset.name], dataset)
            _upsert(session, dataset, rows)
            processed[dataset.name] = len(rows)

    return IngestionResult(processed=processed)
