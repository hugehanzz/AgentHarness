from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AgentHarness"
    app_env: str = "development"
    database_url: str = "mysql+pymysql://agentharness:agentharness@localhost:3306/agentharness"
    command_timeout_seconds: int = 30
    agent_timeout_seconds: int = 600
    codex_app_server_command: str = "codex app-server"
    agent_claude_command: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    google_gemini_base_url: str | None = None
    gemini_proxy_url: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_timeout_seconds: int = 60
    app_timezone: str = "Asia/Shanghai"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
