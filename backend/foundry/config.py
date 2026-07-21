from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOUNDRY_", env_file=".env", extra="ignore")

    secret_key: str = "change-me-in-production"
    database_url: str = ""
    cors_origins: str = (
        "http://localhost:5173,http://localhost:8000,"
        "https://dev.perrinresearch.com,https://foundry.perrinresearch.com"
    )
    token_expire_hours: int = 72
    listen_host: str = "127.0.0.1"
    listen_port: int = 8411
    eval_backend_path: str = ""
    site_deploy_script: Path = Path("/home/bsperrinjr/dev.perrinresearch.com/site/scripts/deploy.sh")
    site_portfolio_file: Path = Path(
        "/home/bsperrinjr/dev.perrinresearch.com/site/src/data/portfolio.ts"
    )
    site_public_dir: Path = Path("/home/bsperrinjr/dev.perrinresearch.com/public")
    site_public_url: str = "https://dev.perrinresearch.com"
    site_deploy_timeout_seconds: int = 300
    eval_api_url: str = "https://foundry.perrinresearch.com/eval"
    eval_email: str = ""
    eval_password: str = ""
    github_token: str = ""
    github_org: str = "perrinresearch"
    github_webhook_secret: str = ""

    @property
    def data_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "data"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.data_dir / 'foundry.db'}"


settings = Settings()
