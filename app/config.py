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

    indeed_base_url: str = "https://apis.indeed.com"
    indeed_delay_seconds: float = 1.0
    indeed_page_size: int = 25
    indeed_timeout_s: float = 30.0
    # Credential + market headers: live in .env only, never in code.
    # Empty key → the source refuses to fire (reported per source in sync).
    indeed_api_key: str = ""
    indeed_country: str = "BR"
    indeed_locale: str = "pt-BR"
    # Transport retries with exponential backoff + jitter (0 = single shot).
    indeed_max_retries: int = 2
    indeed_backoff_seconds: float = 5.0

    glassdoor_base_url: str = "https://www.glassdoor.com"
    # Cloudflare interstitial lasts a few seconds: give the SERP room to settle.
    glassdoor_delay_seconds: float = 2.0
    glassdoor_timeout_ms: int = 30000
    # Headless trips the Cloudflare challenge on this machine; headful passes.
    glassdoor_headless: bool = False

    # Sync service: drop postings older than N hours (0 = keep everything).
    # Default 30 days; the dashboard's sync form overrides it per request.
    hours_old: int = 720
    # Politeness pause between sources during a sync (0 = none).
    sync_delay_seconds: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


settings = Settings()


def ensure_data_dir() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)
