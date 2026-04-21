from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from data_translate.config.models_runtime import RunPolicyOverrideModel


class TranslationRuleModel(BaseModel):
    source: str = Field(min_length=1)
    target: str | None = None
    strategy: str = Field(min_length=1)
    cache: bool = True
    options: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class GoogleTranslationBackendModel(BaseModel):
    provider: Literal["google"] = "google"

    model_config = ConfigDict(extra="forbid")


class DeepLTranslationBackendModel(BaseModel):
    provider: Literal["deepl"] = "deepl"
    api_key_env: str = Field(min_length=1)
    base_url: str = "https://api-free.deepl.com/v2/translate"
    timeout_seconds: float = Field(default=60.0, gt=0)
    formality: str = ""

    model_config = ConfigDict(extra="forbid")


class YandexTranslationBackendModel(BaseModel):
    provider: Literal["yandex"] = "yandex"
    api_key_env: str = Field(min_length=1)
    folder_id: str = ""
    folder_id_env: str = "YANDEX_FOLDER_ID"
    base_url: str = "https://translate.api.cloud.yandex.net/translate/v2/translate"
    timeout_seconds: float = Field(default=60.0, gt=0)
    speller: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_folder_id_source(self) -> "YandexTranslationBackendModel":
        if not self.folder_id and not self.folder_id_env:
            raise ValueError("yandex backend requires folder_id or folder_id_env")
        return self


TranslationBackendModel = Annotated[
    GoogleTranslationBackendModel | DeepLTranslationBackendModel | YandexTranslationBackendModel,
    Field(discriminator="provider"),
]


class TranslationSpecModel(BaseModel):
    source_lang: str = Field(min_length=1)
    target_lang: str = Field(min_length=1)
    drop_columns: list[str] = Field(default_factory=list)
    cache_namespace: str = ""
    backend: TranslationBackendModel = Field(default_factory=GoogleTranslationBackendModel)
    rules: list[TranslationRuleModel] = Field(min_length=1)
    runtime_overrides: RunPolicyOverrideModel = Field(default_factory=RunPolicyOverrideModel)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_rules(self) -> "TranslationSpecModel":
        targets = [str(rule.target or rule.source) for rule in self.rules]
        duplicates = sorted({target for target in targets if targets.count(target) > 1})
        if duplicates:
            raise ValueError(f"translation rules define duplicate target fields: {duplicates}")
        collisions = sorted(set(targets) & set(self.drop_columns))
        if collisions:
            raise ValueError(f"drop_columns overlaps translation targets: {collisions}")
        return self
