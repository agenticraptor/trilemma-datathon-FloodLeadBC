"""Runtime settings, read from the environment (and `.env` when present)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_URL = "https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC"
USER_AGENT = f"FloodLeadBC/0.1 (+{REPO_URL})"

ATTRIBUTION = [
    "Contains information licensed under the Open Government Licence – Canada.",
    "Contains data from Environment and Climate Change Canada.",
    "Credit: U.S. Geological Survey.",
    "Official forecasts and flood categories: NOAA National Weather Service "
    "(not affiliated with or endorsed by NOAA/NWS).",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "floodlead"
    postgres_db: str = "floodlead"

    archive_dir: Path = Path("/srv/floodlead/archive")
    public_hostname: str = ""

    http_timeout_s: float = 60.0
    http_max_parallel: int = 4  # per source, also during backfills

    eccc_base: str = "https://dd.weather.gc.ca/today/hydrometric/csv/BC"
    eccc_ogc_base: str = "https://api.weather.gc.ca"
    usgs_ogc_base: str = "https://api.waterdata.usgs.gov/ogcapi/v1"
    nwps_base: str = "https://api.water.noaa.gov/nwps/v1"

    def dsn(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
