from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/jobs.db"
    profile_path: str = "data/profile.json"
    classifier_backend: str = "laya"  # laya | fake | heuristic
    laya_device: str = ""  # empty = auto (cuda > mps > cpu)
    linkedin_profile_dir: str = "~/.linkedin-laya/profile"
    linkedin_headless: bool = True
    linkedin_delay_seconds: float = 1.0
    linkedin_nav_timeout_ms: int = 30000

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


settings = Settings()


def ensure_data_dir() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)
