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

    geekhunter_base_url: str = "https://www.geekhunter.com"
    geekhunter_delay_seconds: float = 1.0
    geekhunter_page_size: int = 25
    geekhunter_timeout_s: float = 30.0

    gupy_base_url: str = "https://portal.gupy.io"
    gupy_delay_seconds: float = 1.0
    gupy_page_size: int = 10
    gupy_timeout_s: float = 30.0

    glassdoor_base_url: str = "https://www.glassdoor.com"
    # Cloudflare interstitial lasts a few seconds: give the SERP room to settle.
    glassdoor_delay_seconds: float = 2.0
    glassdoor_timeout_ms: int = 30000
    # Headless trips the Cloudflare challenge on this machine; headful passes.
    glassdoor_headless: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


settings = Settings()


def ensure_data_dir() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)
