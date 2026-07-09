"""Application settings loaded from environment and .env."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from project root (stt-bench/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str | None = None
    deepgram_api_key: str | None = None
    assemblyai_api_key: str | None = None

    stt_bench_host: str = "127.0.0.1"
    stt_bench_port: int = 8766
    stt_bench_db_path: str = "./data/results.db"
    stt_bench_cache_dir: str = "./data/cache"
    stt_bench_data_dir: str = "./data"
    stt_bench_config_dir: str = "./config"

    whisper_rpm: int = 50
    deepgram_rpm: int = 100
    whisper_model: str = "whisper-1"
    deepgram_model: str = "nova-2"
    assemblyai_model: str = "best"
    stt_bench_log_level: str = "INFO"
    stt_bench_max_concurrent_samples: int = 4

    @property
    def project_root(self) -> Path:
        return _PROJECT_ROOT

    def resolve_path(self, relative: str) -> Path:
        p = Path(relative)
        if p.is_absolute():
            return p
        return (_PROJECT_ROOT / p).resolve()

    @property
    def data_dir(self) -> Path:
        return self.resolve_path(self.stt_bench_data_dir)

    @property
    def config_dir(self) -> Path:
        return self.resolve_path(self.stt_bench_config_dir)

    @property
    def db_path(self) -> Path:
        return self.resolve_path(self.stt_bench_db_path)

    @property
    def cache_dir(self) -> Path:
        return self.resolve_path(self.stt_bench_cache_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
