from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    data_dir: Path = Path("data")
    docs_v1_path: Path = Path("data/ct200_manual.pdf")
    docs_v2_path: Path = Path("data/ct200_manual_v2.pdf")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
