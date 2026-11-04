import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from app.rag.indexer import index_policy_pdf
from app.rag.retriever import PolicyRetriever


def _loader_factory(pages: list[Document]):
    loader = MagicMock()
    loader.load.return_value = pages
    factory = MagicMock(return_value=loader)
    return factory


def test_indexing_is_idempotent_and_preserves_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "policies.pdf"
    pdf_path.write_bytes(b"stable fake PDF content")
    pages = [Document(page_content="Page one", metadata={"page": 0})]
    chunks = [
        Document(page_content="First policy chunk", metadata={"page": 0}),
        Document(page_content="Second policy chunk", metadata={"page": 0}),
    ]
    splitter = MagicMock()
    splitter.split_documents.return_value = chunks
    vector_store = MagicMock()
    client = MagicMock()
    client.scroll.return_value = ([], None)

    first = index_policy_pdf(
        pdf_path=pdf_path,
        collection_name="policies",
        vector_store=vector_store,
        client=client,
        chunk_size=1000,
        chunk_overlap=150,
        loader_factory=_loader_factory(pages),
        splitter=splitter,
    )
    first_ids = vector_store.add_documents.call_args.kwargs["ids"]

    client.scroll.return_value = (
        [SimpleNamespace(id=point_id) for point_id in first_ids],
        None,
    )
    second = index_policy_pdf(
        pdf_path=pdf_path,
        collection_name="policies",
        vector_store=vector_store,
        client=client,
        chunk_size=1000,
        chunk_overlap=150,
        loader_factory=_loader_factory(pages),
        splitter=splitter,
    )
    second_ids = vector_store.add_documents.call_args.kwargs["ids"]
    indexed_documents = vector_store.add_documents.call_args.args[0]

    assert first_ids == second_ids
    assert len(set(first_ids)) == 2
    assert all(uuid.UUID(point_id) for point_id in first_ids)
    assert indexed_documents[0].metadata["source"] == "policies.pdf"
    assert indexed_documents[0].metadata["page"] == 1
    assert indexed_documents[0].metadata["chunk_index"] == 0
    assert indexed_documents[0].metadata["document_hash"] == first.document_hash
    assert second.stale_chunks_removed == 0
    client.delete.assert_not_called()


def test_indexing_removes_only_stale_chunks_after_upsert(tmp_path: Path) -> None:
    pdf_path = tmp_path / "policies.pdf"
    pdf_path.write_bytes(b"changed fake PDF content")
    pages = [Document(page_content="Page", metadata={"page": 0})]
    splitter = MagicMock()
    splitter.split_documents.return_value = [
        Document(page_content="Current chunk", metadata={"page": 0})
    ]
    vector_store = MagicMock()
    stale_id = str(uuid.uuid4())
    client = MagicMock()
    client.scroll.return_value = ([SimpleNamespace(id=stale_id)], None)

    result = index_policy_pdf(
        pdf_path=pdf_path,
        collection_name="policies",
        vector_store=vector_store,
        client=client,
        chunk_size=500,
        chunk_overlap=50,
        loader_factory=_loader_factory(pages),
        splitter=splitter,
    )

    assert result.stale_chunks_removed == 1
    assert vector_store.add_documents.call_count == 1
    selector = client.delete.call_args.kwargs["points_selector"]
    assert selector.points == [stale_id]


def test_indexing_rejects_pdf_without_extractable_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"fake PDF")

    with pytest.raises(ValueError, match="No pages extracted"):
        index_policy_pdf(
            pdf_path=pdf_path,
            collection_name="policies",
            vector_store=MagicMock(),
            client=MagicMock(),
            chunk_size=1000,
            chunk_overlap=100,
            loader_factory=_loader_factory([]),
        )


def test_retriever_returns_relevant_chunks_with_source_and_page() -> None:
    vector_store = MagicMock()
    vector_store.similarity_search_with_relevance_scores.return_value = [
        (
            Document(
                page_content="Returns are accepted within 30 days.",
                metadata={"source": "policies.pdf", "page": 3},
            ),
            0.91,
        )
    ]
    retriever = PolicyRetriever(vector_store, top_k=3)

    results = retriever.retrieve("What is the return period?")

    vector_store.similarity_search_with_relevance_scores.assert_called_once_with(
        "What is the return period?", k=3
    )
    assert results[0].content == "Returns are accepted within 30 days."
    assert results[0].source == "policies.pdf"
    assert results[0].page == 3
    assert results[0].score == pytest.approx(0.91)


def test_retriever_returns_empty_and_rejects_blank_question() -> None:
    vector_store = MagicMock()
    vector_store.similarity_search_with_relevance_scores.return_value = []
    retriever = PolicyRetriever(vector_store)

    assert retriever.retrieve("unknown policy") == []
    with pytest.raises(ValueError, match="question cannot be empty"):
        retriever.retrieve("   ")
