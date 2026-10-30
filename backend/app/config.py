"""Central configuration. All secrets come from environment variables / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "Multimodal AI Chatbot"
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = "sqlite:///./data/app.db"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    trust_proxy: bool = False

    # --- AI provider ---
    ai_provider: str = "gemini"                        # only "gemini" is supported
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-3.5-flash"        # must support vision
    gemini_embedding_model: str = "gemini-embedding-001"
    # Convenience aliases used inside llm.py so the rest of the app
    # never has to distinguish between providers.
    @property
    def chat_model(self) -> str:
        return self.gemini_chat_model

    @property
    def embedding_model(self) -> str:
        return self.gemini_embedding_model

    chat_fallback_model: str = "gemini-3.5-flash-lite"
    # STT / TTS: Gemini has no native equivalents; audio endpoints are
    # gracefully disabled when no fallback key is set.
    stt_model: str = "whisper-1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    ai_timeout_seconds: float = 60
    ai_max_retries: int = 3
    enable_tools: bool = True

    # --- Files ---
    upload_dir: str = "./data/uploads"
    max_image_mb: int = 10
    max_doc_mb: int = 25
    max_audio_mb: int = 25
    max_pdf_pages: int = 400
    max_ocr_pages: int = 60
    user_storage_mb: int = 500
    file_retention_days: int = 30  # 0 = keep until the user deletes

    tesseract_langs: str = "eng+hin+mar"

    # --- Rate limits (per minute) ---
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 10
    rate_limit_ai_per_minute: int = 30
    rate_limit_default_per_minute: int = 240

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
