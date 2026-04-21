from functools import lru_cache
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentSettings(BaseSettings):
    OPENAI_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    DEEPL_API_KEY: str | None = None
    YANDEX_API_KEY: str | None = None
    YANDEX_FOLDER_ID: str | None = None
    HF_TOKEN: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_environment_settings() -> EnvironmentSettings:
    return EnvironmentSettings()


def get_env_value(name: str, *, required: bool = True) -> str:
    settings = get_environment_settings()
    value = getattr(settings, name, None)
    if value is None:
        value = os.getenv(name)
    if isinstance(value, str) and value:
        return value
    if required:
        raise RuntimeError(f"{name} is not set")
    return ""
