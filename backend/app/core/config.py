"""
Application configuration settings.
Uses pydantic-settings for environment variable management.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache
import hashlib


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "Agrawal Estate Planner"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False  # Set to False for performance - SQLAlchemy won't log queries
    
    # Database
    DATABASE_URL: str = "postgresql://agrawal_user:agrawal_secure_2024@localhost:5432/agrawal_estate"
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    INBOX_DIR: Path = DATA_DIR / "inbox"
    PROCESSED_DIR: Path = DATA_DIR / "processed"
    FAILED_DIR: Path = DATA_DIR / "failed"
    DOCUMENTS_DIR: Path = DATA_DIR / "documents"
    
    # Security
    SECRET_KEY: str = "agrawal-estate-planner-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Family Password - set via environment variable or .env file
    FAMILY_PASSWORD: str = "Alishade@r"
    
    @property
    def PASSWORD_HASH(self) -> str:
        """Compute password hash from FAMILY_PASSWORD."""
        salted = f"{self.SECRET_KEY}:{self.FAMILY_PASSWORD}"
        return hashlib.sha256(salted.encode()).hexdigest()
    
    # Network/CORS - Allow local network access
    # These cover common home network ranges
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # Common home network ranges - frontend served from any local IP
        "http://192.168.0.*:3000",
        "http://192.168.1.*:3000",
        "http://192.168.0.*:5173",
        "http://192.168.1.*:5173",
        "http://10.0.0.*:3000",
        "http://10.0.0.*:5173",
    ]
    
    # Allow all origins in development (for home network)
    CORS_ALLOW_ALL: bool = True
    
    # Notification settings (optional)
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    
    # Email notification settings (optional)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    NOTIFY_EMAIL: Optional[str] = None
    
    # WhatsApp via Twilio (optional)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_FROM: Optional[str] = None
    WHATSAPP_TO: Optional[str] = None
    
    # Plaid API Configuration
    PLAID_CLIENT_ID: Optional[str] = None
    PLAID_SECRET: Optional[str] = None
    PLAID_ENV: str = "sandbox"  # sandbox, development, or production
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields from .env that aren't in the model


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
