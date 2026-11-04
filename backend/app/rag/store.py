from dataclasses import dataclass

from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from app.core.config import Settings, settings


class RAGConfigurationError(RuntimeError):
    """Raised when required RAG configuration is missing or invalid."""


class RAGNotIndexedError(RuntimeError):
    """Raised when retrieval is attempted before indexing policies."""


@dataclass
class PolicyStore:
    client: QdrantClient
    vector_store: QdrantVectorStore

    def close(self) -> None:
        self.client.close()


def _embeddings(config: Settings) -> OpenAIEmbeddings:
    if config.openai_api_key is None or not config.openai_api_key.get_secret_value():
        raise RAGConfigurationError("OPENAI_API_KEY is required for policy RAG")
    return OpenAIEmbeddings(
        model=config.openai_embedding_model,
        api_key=config.openai_api_key.get_secret_value(),
    )


def open_policy_store(
    *,
    create_if_missing: bool,
    config: Settings = settings,
) -> PolicyStore:
    embeddings = _embeddings(config)
    config.qdrant_path.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(config.qdrant_path))
    try:
        if not client.collection_exists(config.qdrant_collection):
            if not create_if_missing:
                raise RAGNotIndexedError(
                    "Policy collection is missing; run the policy index command first"
                )
            probe = embeddings.embed_query("policy vector dimension probe")
            client.create_collection(
                collection_name=config.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=len(probe),
                    distance=models.Distance.COSINE,
                ),
            )

        vector_store = QdrantVectorStore(
            client=client,
            collection_name=config.qdrant_collection,
            embedding=embeddings,
        )
    except Exception:
        client.close()
        raise
    return PolicyStore(client=client, vector_store=vector_store)
