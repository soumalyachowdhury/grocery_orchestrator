from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    customer_lookup_api_url: str = Field(
        default="http://127.0.0.1:3000/api/customer-id",
        description="Customer lookup agent endpoint.",
    )
    customer_lookup_timeout_seconds: float = Field(default=5.0, gt=0)
    store_name: str = Field(default="Fresh Basket Grocery")
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-5-mini")
    openai_transcription_model: str = Field(default="gpt-4o-mini-transcribe")
    use_openai_orchestrator: bool = Field(default=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
