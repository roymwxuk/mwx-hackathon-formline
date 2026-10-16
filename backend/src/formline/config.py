from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_ai_project_endpoint: str = ""
    azure_ai_model_deployment_name: str = "gpt-4.1-mini"
    sim_speed: float = 10.0  # simulated match seconds per real second


settings = Settings()
