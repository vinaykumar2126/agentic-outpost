import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": stale keys left in .env (e.g. old GROQ_*) shouldn't crash startup
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    eventbrite_api_key: str = ""
    gmail_user: str = ""
    gmail_app_password: str = ""
    # Gemini on Vertex AI — auth via Application Default Credentials, no API key
    google_cloud_project: str = ""
    google_cloud_location: str = "global"  # Gemini 3 preview models are served from "global"
    gemini_model: str = "gemini-3-flash-preview"
    gemini_thinking_level: str = "low"
    database_url: str = "sqlite:///./events.db"
    scrape_days_ahead: int = 60
    log_level: str = "INFO"
    # Cloud deployment: shared secret guarding the /scrape/trigger endpoint (unset = open, for local dev)
    scrape_trigger_secret: str = ""
    # Skip the embedded APScheduler in cloud (Cloud Scheduler drives the nightly job instead)
    disable_scheduler: bool = False
    # Frontend origin (Vercel URL) added to CORS allow-list when set
    frontend_origin: str = ""
    LANGSMITH_TRACING: str = "true"
    LANGSMITH_PROJECT: str = "Agentic_outpost"
    LANGSMITH_API_KEY: str = ""





settings = Settings()


# The LangSmith SDK reads its config from os.environ, not from this Settings object.
# Pydantic loads .env into Settings but does NOT export to the process environment, so
# we push the values through here — otherwise tracing silently stays disabled.
if settings.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_TRACING"] = settings.LANGSMITH_TRACING
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
