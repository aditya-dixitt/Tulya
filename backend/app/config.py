"""Runtime configuration.

Everything that differs between a laptop and a CPSE deployment is an environment
variable. Nothing here has a production-safe default that could be left in place
by accident: SECRET_KEY has no default at all, and the seeded demo accounts are
refused outright when ENVIRONMENT=production.

The matching backends deserve a word. The prototype shipped fallbacks for
sentence-transformers, FAISS and RapidFuzz so it could run where those were not
installable. Fallbacks are still allowed in development, but MATCHING_STRICT
(on by default in production) makes the application refuse to start rather than
quietly score with a different algorithm than the one it claims. A system whose
headline numbers come from TF-IDF while the deck says Sentence-BERT is worse
than one that will not boot.
"""
from __future__ import annotations

import pathlib
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # ---- application -----------------------------------------------------
    APP_NAME: str = "TULYA"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: Environment = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api"

    # ---- security --------------------------------------------------------
    # No default. A deployment that forgets this does not start.
    SECRET_KEY: str = Field(min_length=32)
    SESSION_TTL_SECONDS: int = 12 * 3600
    SESSION_COOKIE_NAME: str = "tulya_session"
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    CSRF_HEADER: str = "X-TULYA-CSRF"
    CORS_ORIGINS: str = "http://localhost:5173"
    LOGIN_RATE_LIMIT: str = "10/minute"
    SEED_DEMO_USERS: bool = True

    # ---- database --------------------------------------------------------
    DATABASE_URL: str = "postgresql+psycopg://tulya:tulya@localhost:5432/tulya"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # ---- matching engine -------------------------------------------------
    EMBEDDING_BACKEND: Literal["sbert", "tfidf-svd", "auto"] = "sbert"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    EMBEDDING_BATCH_SIZE: int = 256
    VECTOR_INDEX: Literal["faiss-flatip", "numpy-exact"] = "faiss-flatip"
    FUZZY_BACKEND: Literal["rapidfuzz", "difflib"] = "rapidfuzz"
    MATCHING_STRICT: bool | None = None  # resolved below from ENVIRONMENT

    # fusion weights and decision bands — configurable, not hardcoded at call sites
    W_COS: float = 0.60
    W_FUZ: float = 0.25
    W_ATTR: float = 0.15
    T_DISCARD: float = 0.75
    T_AUTO: float = 0.92
    MIN_COVERAGE: int = 2
    RETRIEVAL_TOPK: int = 20

    # ---- governance ------------------------------------------------------
    SECOND_APPROVAL_VALUE: float = 1_000_000.0

    # ---- LLM (structured extraction only — never a decision maker) -------
    OLLAMA_ENABLED: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    OLLAMA_TIMEOUT_SECONDS: float = 30.0
    OLLAMA_NUM_CTX: int = 2048

    # ---- artefact paths --------------------------------------------------
    DATA_DIR: pathlib.Path = REPO_ROOT / "data"
    ARTIFACT_DIR: pathlib.Path = REPO_ROOT / "data" / "artifacts"

    # ------------------------------------------------------------------
    @field_validator("CORS_ORIGINS")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def strict_backends(self) -> bool:
        """Refuse to silently downgrade to a fallback algorithm."""
        if self.MATCHING_STRICT is not None:
            return self.MATCHING_STRICT
        return self.is_production

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.is_production:
            if self.SEED_DEMO_USERS:
                raise ValueError(
                    "SEED_DEMO_USERS must be false in production — demo credentials "
                    "must never exist in a deployed TULYA instance"
                )
            if self.DEBUG:
                raise ValueError("DEBUG must be false in production")
            if not self.SESSION_COOKIE_SECURE:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production")
            if "localhost" in self.DATABASE_URL and "@localhost" in self.DATABASE_URL:
                # a compose deployment points at the 'db' service, not localhost
                raise ValueError(
                    "DATABASE_URL still points at localhost in production"
                )
        return self

    def describe_backends(self) -> dict:
        """What the engine is configured to use, for /api/health and RESULTS.md."""
        return {
            "embedding_backend": self.EMBEDDING_BACKEND,
            "embedding_model": self.EMBEDDING_MODEL,
            "embedding_dim": self.EMBEDDING_DIM,
            "vector_index": self.VECTOR_INDEX,
            "fuzzy_backend": self.FUZZY_BACKEND,
            "strict": self.strict_backends,
            "weights": {"cos": self.W_COS, "fuz": self.W_FUZ, "attr": self.W_ATTR},
            "thresholds": {"discard": self.T_DISCARD, "auto_suggest": self.T_AUTO},
            "min_coverage": self.MIN_COVERAGE,
            "llm_extraction": self.OLLAMA_MODEL if self.OLLAMA_ENABLED else "disabled",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
