from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"
FRONTEND_ENV_PATH = PROJECT_ROOT / "frontend" / ".env"
CACHE_DIR = PROJECT_ROOT / ".cache"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_csv(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.getenv(name, "").split(",")
        if item.strip()
    )


def configure_model_cache() -> None:
    hf_home = CACHE_DIR / "huggingface"
    sentence_transformers_home = CACHE_DIR / "sentence_transformers"

    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HF_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home / "transformers"))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(sentence_transformers_home))


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    app_env: str
    debug_rag_response: bool

    embedding_model_name: str
    embedding_local_files_only: bool

    default_top_k: int
    max_top_k: int
    default_rerank_top_k: int
    max_rerank_top_k: int
    default_context_max_tokens: int
    max_context_tokens: int

    llm_provider: str
    llm_model: str
    llm_temperature: float
    llm_max_output_tokens: int
    llm_timeout_ms: int
    gemini_api_key: str

    max_question_length: int
    cors_origins: tuple[str, ...]

    supabase_db_host: str
    supabase_db_port: int
    supabase_db_name: str
    supabase_db_user: str
    supabase_db_password: str
    supabase_db_sslmode: str

    supabase_url: str
    supabase_anon_key: str

    monitoring_admin_user_ids: tuple[str, ...]
    monitoring_api_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:3000,http://localhost:5173,http://localhost:8501",
            ).split(",")
            if origin.strip()
        )

        return cls(
            app_name=os.getenv("APP_NAME", "Chatbot Thuế TNCN API"),
            app_version=os.getenv("APP_VERSION", "0.1.0"),
            app_env=os.getenv("APP_ENV", "development").strip().lower() or "development",
            debug_rag_response=_env_bool("DEBUG_RAG_RESPONSE", False),

            embedding_model_name=os.getenv(
                "EMBEDDING_MODEL_NAME",
                "intfloat/multilingual-e5-base",
            ),
            embedding_local_files_only=_env_bool(
                "EMBEDDING_LOCAL_FILES_ONLY",
                True,
            ),

            default_top_k=max(1, _env_int("RAG_DEFAULT_TOP_K", 10)),
            max_top_k=max(1, _env_int("RAG_MAX_TOP_K", 20)),
            default_rerank_top_k=max(
                1,
                _env_int("RAG_DEFAULT_RERANK_TOP_K", 5),
            ),
            max_rerank_top_k=max(
                1,
                _env_int("RAG_MAX_RERANK_TOP_K", 10),
            ),
            default_context_max_tokens=max(
                100,
                _env_int("RAG_DEFAULT_CONTEXT_MAX_TOKENS", 3000),
            ),
            max_context_tokens=max(
                100,
                _env_int("RAG_MAX_CONTEXT_TOKENS", 8000),
            ),

            llm_provider=os.getenv("LLM_PROVIDER", "gemini").strip().lower() or "gemini",
            llm_model=os.getenv("LLM_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash",
            llm_temperature=_env_float("LLM_TEMPERATURE", 0.1),
            llm_max_output_tokens=max(
                1,
                _env_int("LLM_MAX_OUTPUT_TOKENS", 1500),
            ),
            llm_timeout_ms=max(
                1000,
                _env_int("LLM_TIMEOUT_MS", 30000),
            ),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),

            max_question_length=max(
                1,
                _env_int("MAX_QUESTION_LENGTH", 1000),
            ),
            cors_origins=origins,

            supabase_db_host=os.getenv("SUPABASE_DB_HOST", "").strip(),
            supabase_db_port=_env_int("SUPABASE_DB_PORT", 5432),
            supabase_db_name=os.getenv("SUPABASE_DB_NAME", "postgres").strip(),
            supabase_db_user=os.getenv("SUPABASE_DB_USER", "").strip(),
            supabase_db_password=os.getenv("SUPABASE_DB_PASSWORD", "").strip(),
            supabase_db_sslmode=os.getenv(
                "SUPABASE_DB_SSLMODE",
                "require",
            ).strip() or "require",

            supabase_url=(
                os.getenv("SUPABASE_URL", "").strip()
                or os.getenv("VITE_SUPABASE_URL", "").strip()
            ).rstrip("/"),
            supabase_anon_key=(
                os.getenv("SUPABASE_ANON_KEY", "").strip()
                or os.getenv("VITE_SUPABASE_ANON_KEY", "").strip()
            ),

            monitoring_admin_user_ids=_env_csv("MONITORING_ADMIN_USER_IDS"),
            monitoring_api_key=os.getenv("MONITORING_API_KEY", "").strip(),
        )

    @property
    def database_configured(self) -> bool:
        return all(
            [
                self.supabase_db_host,
                self.supabase_db_port,
                self.supabase_db_name,
                self.supabase_db_user,
                self.supabase_db_password,
            ]
        )

    @property
    def llm_configured(self) -> bool:
        return self.llm_provider == "gemini" and bool(self.gemini_api_key)

    @property
    def supabase_auth_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    @property
    def expose_debug_payload(self) -> bool:
        return self.app_env != "production" and self.debug_rag_response

    def database_kwargs(self) -> dict[str, str | int]:
        if not self.database_configured:
            raise RuntimeError(
                "Supabase database is not configured. Set SUPABASE_DB_HOST, "
                "SUPABASE_DB_PORT, SUPABASE_DB_NAME, SUPABASE_DB_USER, and "
                "SUPABASE_DB_PASSWORD in .env."
            )

        return {
            "host": self.supabase_db_host,
            "port": self.supabase_db_port,
            "dbname": self.supabase_db_name,
            "user": self.supabase_db_user,
            "password": self.supabase_db_password,
            "sslmode": self.supabase_db_sslmode,
        }

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_file(ENV_PATH)
    _load_env_file(FRONTEND_ENV_PATH)
    configure_model_cache()
    return Settings.from_env()
