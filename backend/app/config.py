"""Application settings, loaded from environment / backend/.env.

Everything that differs between machines (DB path, LLM provider, API keys)
lives here so nothing secret is ever committed.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "Savo SiteScout"
    database_url: str = f"sqlite:///{(DATA_DIR / 'sitescout.db').as_posix()}"
    upload_dir: Path = BACKEND_DIR / "uploads"
    secret_key: str = "dev-only-change-me"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Savomart stores API (shared in the hackathon brief)
    stores_api_url: str = "https://internal-service.savomart.in/bridge/api/store/list?is_operational=True"
    stores_api_token: str = ""

    # LLM — provider is swappable: none | anthropic | openai (any OpenAI-compatible endpoint:
    # OpenAI, Groq, OpenRouter, Together, Ollama, LM Studio ...)
    llm_provider: str = "none"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout_s: float = 45.0

    # Nominatim (reverse geocoding for field capture) — respect the usage policy
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "SavoSiteScout/0.1 (hackathon demo)"
    enable_reverse_geocode: bool = True

    # OSRM (drive times to existing stores). Public demo server; optional.
    osrm_url: str = "https://router.project-osrm.org"
    enable_osrm: bool = False

    # Catchment reuse policy
    reuse_min_coverage: float = 0.8   # share of the new catchment already surveyed
    reuse_max_age_days: int = 180     # survey data older than this is "stale"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
