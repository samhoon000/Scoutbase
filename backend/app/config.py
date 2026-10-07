from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"), extra="ignore")
    mongodb_uri: str = ""
    database_name: str = "prospectiq"
    demo_mode: bool = True
    cors_origins: str = "http://localhost:3000"
    companies_house_api_key: str = ""
    github_token: str = ""
    sec_user_agent: str = ""
    refresh_days: int = 30
    website_enrichment: bool = False


settings = Settings()
