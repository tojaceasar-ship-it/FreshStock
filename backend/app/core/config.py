from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "FreshStock API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Use pg8000 driver for Vercel compatibility
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+pg8000://freshstock:freshstock_secret@localhost:5432/freshstock")
    DATABASE_URL_ASYNC: str = os.getenv("DATABASE_URL_ASYNC", "postgresql+asyncpg://freshstock:freshstock_secret@localhost:5432/freshstock")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-change-in-production-32chars-min-32")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    BACKEND_CORS_ORIGINS: str = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    RATE_LIMIT_DEFAULT: int = int(os.getenv("RATE_LIMIT_DEFAULT", "120"))
    RATE_LIMIT_AUTH: int = int(os.getenv("RATE_LIMIT_AUTH", "15"))
    DOUBLE_SUBMIT_GUARD_WINDOW: float = float(os.getenv("DOUBLE_SUBMIT_GUARD_WINDOW", "2"))
    
    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip().rstrip("/") for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

settings = Settings()
