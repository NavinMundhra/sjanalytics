"""Configuration management using Pydantic settings"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # WhatsApp Configuration
    WHATSAPP_VERIFY_TOKEN: str = "smartjoules_verify_token_2025"
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None

    # Gupshup Configuration (legacy support)
    GUPSHUP_API_KEY: Optional[str] = None
    GUPSHUP_APP_NAME: Optional[str] = None
    GUPSHUP_SOURCE_NUMBER: Optional[str] = None

    # LLM Configuration
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "openai/gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.0  # Deterministic responses

    # Google Gemini (fallback)
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_MODEL: str = "gemini-2.0-flash"

    # Database Configuration
    SQLITE_DB_PATH: str = "sj_bot/data/metrics.db"

    # AWS S3 Configuration (for data loading)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_SESSION_TOKEN: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: Optional[str] = None

    # API Security
    API_KEY: str = "dev_api_key_change_in_production"

    # Application
    BASE_URL: str = "http://localhost:8000"
    LOG_LEVEL: str = "INFO"

    # Chart Configuration
    CHART_DEFAULT_WIDTH: int = 1200
    CHART_DEFAULT_HEIGHT: int = 800
    CHART_DPI: int = 150

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
