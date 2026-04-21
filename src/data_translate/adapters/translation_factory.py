from data_translate.adapters.deepl_translate import DeepLTranslateAdapter
from data_translate.adapters.google_translate import GoogleTranslateAdapter
from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.adapters.yandex_translate import YandexTranslateAdapter
from data_translate.config.models_dataset_translation import (
    DeepLTranslationBackendModel,
    GoogleTranslationBackendModel,
    TranslationBackendModel,
    YandexTranslationBackendModel,
)
from data_translate.config.models_runtime_policies import TranslationRunPolicyModel
from data_translate.domain.languages import language_code



def _deepl_lang(value: str) -> str:
    return language_code(value).replace("_", "-").upper()



def _yandex_lang(value: str) -> str:
    return language_code(value).replace("_", "-").lower()



def build_translation_adapter(
    *,
    source_lang: str,
    target_lang: str,
    runtime: TranslationRunPolicyModel,
    backend: TranslationBackendModel,
    cache_dir: str,
) -> TranslationAdapter:
    if isinstance(backend, GoogleTranslationBackendModel):
        return GoogleTranslateAdapter(
            source_lang=language_code(source_lang),
            target_lang=language_code(target_lang),
            max_retries=runtime.max_retries,
            retry_sleep=runtime.retry_sleep,
            thread_limit=runtime.concurrency,
            cache_dir=cache_dir,
        )
    if isinstance(backend, DeepLTranslationBackendModel):
        return DeepLTranslateAdapter(
            source_lang=_deepl_lang(source_lang),
            target_lang=_deepl_lang(target_lang),
            api_key_env=backend.api_key_env,
            base_url=backend.base_url,
            timeout_seconds=backend.timeout_seconds,
            formality=backend.formality,
            max_retries=runtime.max_retries,
            retry_sleep=runtime.retry_sleep,
            thread_limit=runtime.concurrency,
            cache_dir=cache_dir,
        )
    if isinstance(backend, YandexTranslationBackendModel):
        return YandexTranslateAdapter(
            source_lang=_yandex_lang(source_lang),
            target_lang=_yandex_lang(target_lang),
            api_key_env=backend.api_key_env,
            folder_id=backend.folder_id,
            folder_id_env=backend.folder_id_env,
            base_url=backend.base_url,
            timeout_seconds=backend.timeout_seconds,
            speller=backend.speller,
            max_retries=runtime.max_retries,
            retry_sleep=runtime.retry_sleep,
            thread_limit=runtime.concurrency,
            cache_dir=cache_dir,
        )
    raise ValueError(f"unsupported translation backend: {backend}")
