"""Core configuration and settings for UniMind."""

from typing import List, Union
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json

DEFAULT_DEV_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables."""

    # Project Information
    PROJECT_NAME: str = "UniMind Knowledge Assistant"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS Settings
    ALLOWED_ORIGINS: Union[List[str], str] = list(DEFAULT_DEV_ORIGINS)
    CORS_ALLOW_CREDENTIALS: bool = True

    @property
    def cors_allow_credentials(self) -> bool:
        """Ensure wildcard origin ('*') is never combined with allow_credentials=True per CORS specifications."""
        if "*" in self.ALLOWED_ORIGINS:
            return False
        return self.CORS_ALLOW_CREDENTIALS

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        origins = [str(i).strip() for i in parsed if str(i).strip()]
                        return origins if origins else list(DEFAULT_DEV_ORIGINS)
                except Exception:
                    pass
            origins = [i.strip() for i in v.split(",") if i.strip()]
            return origins if origins else list(DEFAULT_DEV_ORIGINS)
        elif isinstance(v, list):
            origins = [str(i).strip() for i in v if str(i).strip()]
            return origins if origins else list(DEFAULT_DEV_ORIGINS)
        return list(DEFAULT_DEV_ORIGINS)

    # Storage and Knowledge Base Paths
    DATA_RAW_DIR: str = "data/raw"
    DATA_PROCESSED_DIR: str = "data/processed"
    DATA_EVALUATION_DIR: str = "data/evaluation"
    VECTOR_STORE_DIR: str = "vector_store"
    SQLITE_DB_PATH: str = "data/unimind.db"

    # Upload Constraints & Security
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = [".pdf"]
    ALLOWED_UPLOAD_MIME_TYPES: List[str] = ["application/pdf"]

    # Model Settings (Placeholders for upcoming phases)
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODEL: str = "gemini-1.5-flash"

    def get_gemini_api_key(self) -> str:
        """Safely expose the raw API key secret string only when explicitly invoking the LLM client."""
        return self.GEMINI_API_KEY.get_secret_value()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()

