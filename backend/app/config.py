from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    eventbrite_api_key: str = ""
    gmail_user: str = ""
    gmail_app_password: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"
    database_url: str = "sqlite:///./events.db"
    scrape_days_ahead: int = 60
    log_level: str = "INFO"


settings = Settings()
