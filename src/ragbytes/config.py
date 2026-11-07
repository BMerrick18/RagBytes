from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAGBYTES_")

    app_name: str = "RagBytes API"
    version: str = "dev"
    stats_path: str = "data/stats.db"
    # Server key for semantic chunking. Empty means that tier is unavailable.
    openai_api_key: SecretStr = SecretStr("")
    # text-embedding-3-large separates subjects more sharply, at a higher price.
    semantic_model: str = "text-embedding-3-small"


settings = Settings()
