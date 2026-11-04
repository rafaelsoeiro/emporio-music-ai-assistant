import argparse
from pathlib import Path

from app.db.session import SessionLocal
from app.services.csv_ingestion import CSVIngestionError, ingest_csv_directory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest the store CSV datasets")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("app/data"),
        help="directory containing the six CSV datasets",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with SessionLocal() as session:
            result = ingest_csv_directory(session, args.data_dir)
    except CSVIngestionError as exc:
        print(f"Ingestion failed: {exc}")
        return 1

    for dataset, count in result.processed.items():
        print(f"{dataset}: {count} rows processed")
    print(f"total: {result.total} rows processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
