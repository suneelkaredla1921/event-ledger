from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _candidate_directories(start: Path) -> list[Path]:
    """Directories to search for .env (no fixed parent depth; Docker-safe)."""
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(directory: Path) -> None:
        resolved = str(directory.resolve())
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(directory)

    add(Path.cwd())
    add(start.parent)
    for parent in start.parents:
        add(parent)
    return candidates


def _env_files() -> tuple[str, ...]:
    """Discover .env files from cwd, package dir, and ancestors of this module."""
    seen_files: set[str] = set()
    files: list[str] = []
    for base in _candidate_directories(Path(__file__).resolve()):
        path = base / ".env"
        key = str(path.resolve())
        if path.is_file() and key not in seen_files:
            seen_files.add(key)
            files.append(str(path))
    return tuple(files)


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    account_service_url: str = "http://localhost:8001"
    account_request_timeout: float = 2.0
    account_max_retries: int = 3
    account_backoff_base: float = 0.1
    gateway_database_url: str = "sqlite:///./gateway.db"


@lru_cache
def get_settings() -> GatewaySettings:
    return GatewaySettings()
