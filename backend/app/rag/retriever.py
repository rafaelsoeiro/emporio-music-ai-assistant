from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.documents import Document

from app.core.config import Settings, settings
from app.rag.store import open_policy_store


@dataclass(frozen=True)
class RetrievedPolicyChunk:
    content: str
    source: str
    page: int
    score: float


class PolicyRetriever:
    def __init__(
        self,
        vector_store,
        *,
        top_k: int = 4,
        close_callback: Callable[[], None] | None = None,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self._vector_store = vector_store
        self._top_k = top_k
        self._close_callback = close_callback

    @classmethod
    def from_settings(cls, config: Settings = settings) -> "PolicyRetriever":
        store = open_policy_store(create_if_missing=False, config=config)
        return cls(
            store.vector_store,
            top_k=config.rag_top_k,
            close_callback=store.close,
        )

    def close(self) -> None:
        if self._close_callback is not None:
            self._close_callback()
            self._close_callback = None

    def __enter__(self) -> "PolicyRetriever":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def retrieve(self, question: str) -> list[RetrievedPolicyChunk]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question cannot be empty")

        results: list[tuple[Document, float]] = (
            self._vector_store.similarity_search_with_relevance_scores(
                normalized_question,
                k=self._top_k,
            )
        )
        return [
            RetrievedPolicyChunk(
                content=document.page_content,
                source=str(document.metadata.get("source", "unknown")),
                page=int(document.metadata.get("page", 0)),
                score=float(score),
            )
            for document, score in results
        ]
