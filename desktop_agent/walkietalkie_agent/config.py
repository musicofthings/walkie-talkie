"""Configuration management for WalkieTalkie Desktop Agent."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Runtime settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="WALKIETALKIE_", extra="ignore")

    env: str = "development"
    log_level: str = "INFO"
    debug: bool = False

    bind_host: str = "0.0.0.0"
    bind_port: int = 8765
    advertised_host: str = "127.0.0.1"
    desktop_target: str = "claude"

    token_ttl_seconds: int = 900
    model_size: str = "small"
    compute_type: str = "int8"
    language: str = "en"

    auto_send: bool = True
    require_confirmation: bool = False

    action_log_path: Path = Field(default=Path("logs/actions.log"))


settings = AgentSettings()
