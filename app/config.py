"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GRADEOPS"
    debug: bool = False
    # development | test | production. Production refuses insecure defaults.
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"

    database_url: str = Field(
        default="postgresql+asyncpg://gradeops:gradeops@localhost:5432/gradeops",
        description="Async SQLAlchemy database URL",
    )
    # Schema is managed by Alembic (`alembic upgrade head`). Only enable this for
    # throwaway local experiments; it runs `create_all` on startup.
    db_auto_create: bool = False

    upload_dir: Path = Path("uploads")
    output_dir: Path = Path("outputs")
    models_cache_dir: Path = Path("models_cache")

    # Storage backend: local | s3
    storage_backend: Literal["local", "s3"] = "local"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"
    s3_bucket: str | None = None
    s3_prefix: str = "gradeops"

    ocr_engine: Literal["florence2", "nougat", "tesseract", "easyocr", "paddleocr"] = "florence2"
    ocr_device: str = "cpu"
    ocr_preprocess: bool = True
    florence_model_id: str = "microsoft/Florence-2-base"
    nougat_model_id: str = "facebook/nougat-base"

    embedding_model_id: str = "sentence-transformers/all-MiniLM-L6-v2"
    similarity_threshold: float = 0.55
    blank_answer_min_chars: int = 3
    plagiarism_similarity_threshold: float = 0.92
    # What to do when the sentence-embedding model cannot be loaded (offline host):
    # "lexical" = grade with keyword matching only (reduced confidence, flagged);
    # "error" = fail the evaluation.
    embedding_fallback: Literal["lexical", "error"] = "lexical"

    # AI backends (all optional — heuristic grading remains default)
    ai_backend: Literal["none", "openai", "gemini", "huggingface"] = "none"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    huggingface_api_key: str | None = None
    huggingface_model: str = "meta-llama/Llama-3.2-3B-Instruct"
    use_llm_reasoning: bool = False

    pdf_dpi: int = 200
    max_upload_mb: int = 50
    batch_max_workers: int = 2

    # Auth is ON by default. AUTH_ENABLED=false re-enables the legacy anonymous
    # single-user workbench endpoints (local demos only — anyone can read any
    # submission). Role dashboards (/professor, /ta) always require login.
    auth_enabled: bool = True
    # Self-registration only ever creates TA accounts (no course access until a
    # professor adds them). Professors are provisioned via scripts/create_user.py.
    allow_self_registration: bool = True
    jwt_secret_key: str = "change-me-in-production-use-openssl-rand"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def effective_ai_backend(self) -> str:
        if self.ai_backend != "none":
            return self.ai_backend
        if self.use_llm_reasoning and self.openai_api_key:
            return "openai"
        return "none"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.models_cache_dir.mkdir(parents=True, exist_ok=True)
    return settings
