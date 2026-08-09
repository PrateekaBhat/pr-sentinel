from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, populated from environment variables / .env."""

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"
    github_token: str = ""
    cors_origins: str = "http://localhost:5173"

    # Repository RAG
    rag_enabled: bool = True
    chroma_persist_dir: str = "./chroma_data"
    rag_max_doc_files: int = 12
    rag_max_doc_chars: int = 4000
    rag_top_k: int = 5

    # Analysis history (SQLite — no new database dependency)
    history_db_path: str = "./pr_sentinel_history.db"

    # Specialist agent context limits — how much of a domain's matched files/patches
    # is actually shown to the LLM. Defaults match the previous hardcoded values in
    # agents/nodes.py; env vars (MAX_FILES_PER_AGENT / MAX_PATCH_LINES / MAX_PATCH_CHARS)
    # override them.
    max_files_per_agent: int = 4
    max_patch_lines: int = 30
    max_patch_chars: int = 600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
