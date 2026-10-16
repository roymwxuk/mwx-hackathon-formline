from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_ai_project_endpoint: str = ""
    azure_ai_model_deployment_name: str = "gpt-4.1-mini"
    sim_speed: float = 10.0  # simulated match seconds per real second
    data_dir: Path = BACKEND_DIR / "data"
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
