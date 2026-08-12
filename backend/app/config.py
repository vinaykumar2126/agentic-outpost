import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    eventbrite_api_key: str = ""
    gmail_user: str = ""
    gmail_app_password: str = ""
    groq_api_key: str = ""
    groq_model: str = ""
    database_url: str = "sqlite:///./events.db"
    scrape_days_ahead: int = 60
    log_level: str = "INFO"
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
