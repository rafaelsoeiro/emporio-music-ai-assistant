import argparse
from pathlib import Path

from app.core.config import settings
from app.rag.indexer import index_policy_pdf
from app.rag.store import RAGConfigurationError, open_policy_store


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index the store policy PDF")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=settings.rag_pdf_path,
        help="policy PDF path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        store = open_policy_store(create_if_missing=True)
        try:
            result = index_policy_pdf(
                pdf_path=args.pdf,
                collection_name=settings.qdrant_collection,
                vector_store=store.vector_store,
                client=store.client,
                chunk_size=settings.rag_chunk_size,
                chunk_overlap=settings.rag_chunk_overlap,
            )
        finally:
            store.close()
    except (FileNotFoundError, ValueError, RAGConfigurationError) as exc:
        print(f"Policy indexing failed: {exc}")
        return 1

    print(
        f"Indexed {result.chunks} chunks from {result.pages} pages "
        f"({result.stale_chunks_removed} stale chunks removed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
