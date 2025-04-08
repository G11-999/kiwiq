"""
Configuration settings for the KiwiQ Backend Service.

This module contains all the configuration settings for the application, loaded from
environment variables with sensible defaults.
"""
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

from global_config.settings import ENV_FILE_PATH, Settings

class Settings(Settings):
    """Application settings loaded from environment variables."""
    # TODO: get these vars from environment directly, and ensure order of loading from env or ENV_FILE!

    AWS_BEDROCK_SECRET_ACCESS_KEY: str = ""
    AWS_BEDROCK_ACCESS_KEY_ID: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    FIREWORKS_API_KEY: str = ""
    PPLX_API_KEY: str = ""
    
    # model_config = SettingsConfigDict(
    #     env_file=ENV_FILE_PATH,
    #     env_file_encoding="utf-8",
    #     case_sensitive=True,
    #     extra='ignore',
    # )

# Create a global settings instance
settings = Settings() 
