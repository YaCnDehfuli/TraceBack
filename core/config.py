"""All settings come from environment variables or the local .env file (see .env.example).

Secrets are SecretStr, so they never show up in logs or reprs. Read them with .get_secret_value().
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # MongoDB Atlas
    mongodb_uri: SecretStr = SecretStr("")
    mongodb_db: str = "traceback_dev"

    # Practice-app database used only by the runner (local Docker by default)
    fixture_mongodb_uri: SecretStr = SecretStr("mongodb://localhost:27018")

    # Voyage embeddings through Atlas AI Model APIs (fallback: https://api.voyageai.com/v1 + a Voyage key)
    voyage_api_key: SecretStr = SecretStr("")
    voyage_base_url: str = "https://ai.mongodb.com/v1"
    embedding_model: str = "voyage-4-lite"
    embedding_dimensions: int = 1024

    # LLM
    llm_provider: str = "anthropic"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""

    # ElevenLabs voice agent "Traceback On-Call" (agent id is not secret; the API key is optional)
    elevenlabs_agent_id: str = ""
    elevenlabs_api_key: SecretStr = SecretStr("")

    # Agent budgets
    agent_max_tool_calls: int = 8
    agent_max_patch_attempts: int = 2
    agent_deadline_seconds: int = 120

    # Demo identities: API key -> principal fields (camelCase JSON in .env)
    demo_principals: dict[str, dict[str, Any]] = Field(default_factory=dict)


@lru_cache
def get_settings() -> Settings:
    return Settings()
