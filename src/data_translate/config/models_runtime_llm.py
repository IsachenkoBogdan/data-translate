from pydantic import BaseModel, ConfigDict, Field


class LLMSettingsModel(BaseModel):
    provider: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
    base_url: str = ""
    model: str = Field(min_length=1)
    temperature: float = 0.0
    site_url: str = ""
    app_name: str = ""
    extra_headers: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class LLMSettingsOverrideModel(BaseModel):
    provider: str | None = None
    api_key_env: str | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = None
    site_url: str | None = None
    app_name: str | None = None
    extra_headers: dict[str, str] | None = None

    model_config = ConfigDict(extra="forbid")


class PromptSettingsModel(BaseModel):
    prompt_file: str = Field(min_length=1)
    system_prompt_file: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


class PromptSettingsOverrideModel(BaseModel):
    prompt_file: str | None = None
    system_prompt_file: str | None = None

    model_config = ConfigDict(extra="forbid")
