from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Emporio Music API"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/app.db"
    openai_api_key: SecretStr | None = None
    openai_chat_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    qdrant_path: Path = Path("./data/qdrant")
    qdrant_collection: str = "store_policies"
    rag_pdf_path: Path = Path("./app/data/políticas_da_loja.pdf")
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 150
    rag_top_k: int = 4
    agent_max_tool_iterations: int = 6
    agent_history_messages: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_rag_settings(self) -> "Settings":
        if self.rag_chunk_size <= 0:
            raise ValueError("RAG_CHUNK_SIZE must be positive")
        if self.rag_chunk_overlap < 0:
            raise ValueError("RAG_CHUNK_OVERLAP cannot be negative")
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        if self.rag_top_k <= 0:
            raise ValueError("RAG_TOP_K must be positive")
        if self.agent_max_tool_iterations <= 0:
            raise ValueError("AGENT_MAX_TOOL_ITERATIONS must be positive")
        if self.agent_history_messages < 0:
            raise ValueError("AGENT_HISTORY_MESSAGES cannot be negative")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
