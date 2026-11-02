from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHARK_BYTE_")

    app_name: str = "RagBytes API"
    version: str = "dev"
    stats_path: str = "data/stats.db"


settings = Settings()
