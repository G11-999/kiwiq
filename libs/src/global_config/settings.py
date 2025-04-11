"""
Configuration settings for the KiwiQ Backend Service.

This module contains all the configuration settings for the application, loaded from
environment variables with sensible defaults.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional, Literal
# from global_config.logger import setup_logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
LOG_ROOT = PROJECT_ROOT / "logs"

# Ensure DATA_ROOT directory exists
if not DATA_ROOT.exists():
    try:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        print(f"Created data directory at {DATA_ROOT}")
    except Exception as e:
        print(f"Warning: Failed to create data directory at {DATA_ROOT}: {e}")


ENV_FILE_PATH = PROJECT_ROOT / ".env"
PROD_ENV_FILE_PATH = PROJECT_ROOT / ".env.prod"

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    # TODO: get these vars from environment directly, and ensure order of loading from env or ENV_FILE!
    
    # Project metadata
    PROJECT_NAME: str = "KiwiQ Backend"
    VERSION: str = "0.1.0"

    APP_ENV: Literal["DEV", "STAGE", "PROD"] = "DEV"
    
    # Database settings
    DATABASE_URL: str = ""  # Default Postgres for development
    LANGGRAPH_DATABASE_NAME: str = "langgraph_db"
    LANGGRAPH_DATABASE_URL: Optional[str] = None
    DB_ECHO: bool = os.getenv("DB_ECHO_STR", "false").lower() == "true"  # SQL query logging
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_TABLE_NAMESPACE_PREFIX: str = "kiwiq_"
    
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
    MONGO_URL: Optional[str] = None
    RABBITMQ_URL: Optional[str] = None
    CACHE_TTL: int = 3600  # seconds
    
    # Worker pool settings
    WORKER_POOL_SIZE: int = 4

    # LinkedIn integration settings
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    LINKEDIN_ACCESS_TOKEN: str = ""
    LINKEDIN_API_VERSION: str = "202502"
    LINKEDIN_REDIRECT_URL: str = ""

    LOG_LEVEL: str = "WARNING"
    LOG_FILE_NAME: str = "kiwiq_backend.log"
    
    model_config = SettingsConfigDict(
        env_file=(ENV_FILE_PATH if os.getenv("APP_ENV", "DEV") == "DEV" else PROD_ENV_FILE_PATH),
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
global_settings = Settings() 
if not global_settings.LANGGRAPH_DATABASE_URL:
    global_settings.LANGGRAPH_DATABASE_URL = "/".join(global_settings.DATABASE_URL.split("/")[:-1] + [global_settings.LANGGRAPH_DATABASE_NAME])
# print(global_settings.DATABASE_URL)
# Setup up global logging for this module

