"""
Configuration settings for the KiwiQ Backend Service.

This module contains all the configuration settings for the application, loaded from
environment variables with sensible defaults.
"""
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

project_root = Path(__file__).resolve().parent.parent.parent.parent
ENV_FILE_PATH = project_root / ".env"

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Project metadata
    PROJECT_NAME: str = "KiwiQ Backend"
    VERSION: str = "0.1.0"
    
    # Database settings
    DATABASE_URL: str = ""  # Default SQLite for development
    DB_ECHO: bool = False  # SQL query logging
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    
    # API settings
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    
    # Registry service settings
    REGISTRY_CACHE_TTL: int = 3600  # seconds
    
    # Workflow execution settings
    MAX_WORKFLOW_LOOPS: int = 1000
    EXECUTION_TIMEOUT: int = 3600  # seconds
    MAX_TOKEN_BUDGET: int = 10000
    
    # Cache settings
    REDIS_URL: Optional[str] = None
    CACHE_TTL: int = 3600  # seconds
    
    # Worker pool settings
    WORKER_POOL_SIZE: int = 4
    
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )
    
    def get_database_settings(self) -> Dict[str, Any]:
        """Get all database-related settings as a dictionary."""
        return {
            "url": self.DATABASE_URL,
            "echo": self.DB_ECHO,
            "pool_size": self.DB_POOL_SIZE,
            "max_overflow": self.DB_MAX_OVERFLOW,
        }


# Create a global settings instance
settings = Settings() 