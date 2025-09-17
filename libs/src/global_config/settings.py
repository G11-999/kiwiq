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
from pydantic import Field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()  # ".env.prod" WORKS!

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


PROD_ENV_FILE_PATH = PROJECT_ROOT / ".env.prod"
ENV_FILE_PATH = PROJECT_ROOT / ".env"

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    # TODO: get these vars from environment directly, and ensure order of loading from env or ENV_FILE!
    
    # Project metadata
    PROJECT_NAME: str = "KiwiQ Backend"
    VERSION: str = "0.1.0"

    APP_ENV: Literal["DEV", "STAGE", "PROD"] = "DEV"
    
    # Database settings
    # Adding default URL which is parsable so SQL Alchemy doesn't throw errors if sessions file is imported!
    DATABASE_URL: str = "postgresql://db_admin:db_admin_password@localhost/db_name"  # Default Postgres for development
    LANGGRAPH_DATABASE_NAME: str = "langgraph_db"
    LANGGRAPH_DATABASE_URL: Optional[str] = None
    DB_ECHO: bool = os.getenv("DB_ECHO_STR", "false").lower() == "true"  # SQL query logging
    DB_TABLE_NAMESPACE_PREFIX: str = "kiwiq_"

    # Main app settings - Optimized for single async worker production load
    # Single async worker can handle 500-2000+ concurrent requests
    # Assuming 40% need DB access with 25% connection utilization = ~50-200 connections needed
    # Total: 75 + 50 = 125 connections max (conservative for production)
    DB_POOL_SIZE: int = 75  # Persistent connections in the pool (warm connections)
    DB_MAX_OVERFLOW: int = 50  # Additional connections for traffic spikes
    
    # Worker/Prefect settings (smaller pools)
    WORKER_DB_POOL_SIZE: int = 2
    WORKER_DB_MAX_OVERFLOW: int = 3
    WORKER_POOL_MAX_SIZE: int = 3

    WORKER_MEDIUM_POOL_SIZE: int = 10
    WORKER_MEDIUM_MAX_OVERFLOW: int = 15 # additive with pool size for max size
    WORKER_MEDIUM_LANGGRAPH_POOL_SIZE: int = 10
    WORKER_MEDIUM_LANGGRAPH_POOL_MAX_SIZE: int = 25  # max upper bound
    WORKER_MEDIUM_POOL_TIMEOUT: int = 45

    WORKER_LARGE_POOL_SIZE: int = 20
    WORKER_LARGE_MAX_OVERFLOW: int = 30  # additive with pool size for max size
    WORKER_LARGE_LANGGRAPH_POOL_SIZE: int = 20
    WORKER_LARGE_LANGGRAPH_POOL_MAX_SIZE: int = 50  # max upper bound
    WORKER_LARGE_POOL_TIMEOUT: int = 60

    # # Worker/Prefect settings - MUST support 50 concurrent workflows
    # # Each workflow needs ~3 connections (checkpointer, DB ops, external context)
    # # Recommended: 50 workflows × 3 connections = 150, with some pooling efficiency
    # # Setting to 100 base + 50 overflow = 150 total connections
    # WORKER_DB_POOL_SIZE: int = 100  # Base pool for concurrent workflows
    # WORKER_DB_MAX_OVERFLOW: int = 50  # Burst capacity for peak load

    # Detect if running in worker
    IS_WORKER_PROCESS: bool = Field(default_factory=lambda: os.getenv("IS_PREFECT_WORKER", "false").lower() == "true")
    
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
    WEAVIATE_HOST: Optional[str] = None
    WEAVIATE_URL: Optional[str] = None
    WEAVIATE_API_KEY: Optional[str] = None
    CACHE_TTL: int = 3600  # seconds

    SCRAPING_SERVER_URL: Optional[str] = None

    LOG_LEVEL: str = "INFO"
    LOG_FILE_NAME: str = "kiwiq_backend.log"
    LOG_PREFECT_FILE_NAME: str = "prefect_worker.log"
    
    model_config = SettingsConfigDict(
        env_file=(ENV_FILE_PATH if os.getenv("APP_ENV", "DEV") == "DEV" else PROD_ENV_FILE_PATH),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    @property
    def effective_pool_size(self) -> int:
        return self.WORKER_DB_POOL_SIZE if self.IS_WORKER_PROCESS else self.DB_POOL_SIZE
    
    @property
    def effective_max_overflow(self) -> int:
        return self.WORKER_DB_MAX_OVERFLOW if self.IS_WORKER_PROCESS else self.DB_MAX_OVERFLOW
    
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

