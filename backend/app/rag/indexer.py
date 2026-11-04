import hashlib
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import models


class DocumentLoader(Protocol):
    def load(self) -> list[Document]: ...


class DocumentSplitter(Protocol):
    def split_documents(self, documents: Sequence[Document]) -> list[Document]: ...


class VectorStore(Protocol):
    def add_documents(self, documents: list[Document], ids: list[str]) -> list[str]: ...


class QdrantIndexClient(Protocol):
    def scroll(self, **kwargs): ...

    def delete(self, **kwargs): ...


@dataclass(frozen=True)
class IndexingResult:
    source: str
    pages: int
    chunks: int
    stale_chunks_removed: int
    document_hash: str


def _source_id(pdf_path: Path) -> str:
    return hashlib.sha256(pdf_path.name.encode("utf-8")).hexdigest()


def _document_hash(pdf_path: Path) -> str:
    digest = hashlib.sha256()
    with pdf_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _chunk_id(source_id: str, document: Document, chunk_index: int) -> str:
    page = document.metadata.get("page", 0)
    content_hash = hashlib.sha256(document.page_content.encode("utf-8")).hexdigest()
    identity = f"{source_id}:{page}:{chunk_index}:{content_hash}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


def _existing_source_ids(
    client: QdrantIndexClient,
    collection_name: str,
    source_id: str,
) -> set[str]:
    existing: set[str] = set()
    offset = None
    source_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.source_id",
                match=models.MatchValue(value=source_id),
            )
        ]
    )

    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=source_filter,
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        existing.update(str(point.id) for point in points)
        if offset is None:
            return existing


def index_policy_pdf(
    *,
    pdf_path: Path,
    collection_name: str,
    vector_store: VectorStore,
    client: QdrantIndexClient,
    chunk_size: int,
    chunk_overlap: int,
    loader_factory: Callable[[str], DocumentLoader] = PyPDFLoader,
    splitter: DocumentSplitter | None = None,
) -> IndexingResult:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Policy PDF not found: {pdf_path}")
    if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("Invalid chunk size or overlap")

    pages = loader_factory(str(pdf_path)).load()
    if not pages:
        raise ValueError(f"No pages extracted from policy PDF: {pdf_path}")

    text_splitter = splitter or RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    raw_chunks = text_splitter.split_documents(pages)
    raw_chunks = [chunk for chunk in raw_chunks if chunk.page_content.strip()]
    if not raw_chunks:
        raise ValueError(f"No text extracted from policy PDF: {pdf_path}")

    source_id = _source_id(pdf_path)
    file_hash = _document_hash(pdf_path)
    chunks: list[Document] = []
    chunk_ids: list[str] = []
    for index, raw_chunk in enumerate(raw_chunks):
        original_page = int(raw_chunk.metadata.get("page", 0))
        chunk = Document(
            page_content=raw_chunk.page_content,
            metadata={
                **raw_chunk.metadata,
                "source": pdf_path.name,
                "source_id": source_id,
                "page": original_page + 1,
                "chunk_index": index,
                "document_hash": file_hash,
            },
        )
        chunks.append(chunk)
        chunk_ids.append(_chunk_id(source_id, chunk, index))

    existing_ids = _existing_source_ids(client, collection_name, source_id)
    vector_store.add_documents(chunks, ids=chunk_ids)

    stale_ids = sorted(existing_ids - set(chunk_ids))
    if stale_ids:
        client.delete(
            collection_name=collection_name,
            points_selector=models.PointIdsList(points=stale_ids),
            wait=True,
        )

    return IndexingResult(
        source=pdf_path.name,
        pages=len(pages),
        chunks=len(chunks),
        stale_chunks_removed=len(stale_ids),
        document_hash=file_hash,
    )
