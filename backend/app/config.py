from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    eventbrite_api_key: str = ""
    gmail_user: str = ""
    gmail_app_password: str = ""
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    database_url: str = "sqlite:///./events.db"
    scrape_days_ahead: int = 60
    log_level: str = "INFO"
    LANGSMITH_TRACING: str = "true"
    LANGSMITH_PROJECT: str = "Agentic_outpost"
    LANGSMITH_API_KEY: str = ""




settings = Settings()
