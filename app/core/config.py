from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

# Find .env file - check app/ directory first, then project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
APP_ENV = BASE_DIR / "app" / ".env"
ROOT_ENV = BASE_DIR / ".env"

# Use app/.env if it exists, otherwise try root .env
env_file = str(APP_ENV) if APP_ENV.exists() else (str(ROOT_ENV) if ROOT_ENV.exists() else ".env")


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # SMTP
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: Optional[str] = None
    REPLY_TO_EMAIL: Optional[str] = None
    
    # AI
    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_MODEL: str = "llama3-groq-70b-8192-tool-use"
    
    # Feature Flags
    ENABLE_AI_CHAT: bool = True
    ENABLE_DOCUMENT_UPLOAD: bool = True
    
    # Application
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = env_file
        case_sensitive = True


settings = Settings()

# Derived paths
UPLOADS_DIR = BASE_DIR / "uploads"
DEPOSIT_PROOFS_DIR = UPLOADS_DIR / "deposit_proofs"
BANK_STATEMENTS_DIR = UPLOADS_DIR / "bank_statements"
CONSTITUTION_UPLOADS_DIR = UPLOADS_DIR / "constitution"
