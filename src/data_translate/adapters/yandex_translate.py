import httpx

from data_translate.adapters.http_translation_base import BaseCachedHttpTranslationAdapter
from data_translate.config.settings import get_env_value


class YandexTranslateAdapter(BaseCachedHttpTranslationAdapter):
    provider_name = "yandex"

    def __init__(
        self,
        *,
        source_lang: str,
        target_lang: str,
        api_key_env: str,
        folder_id: str,
        folder_id_env: str,
        base_url: str,
        timeout_seconds: float,
        speller: bool,
        max_retries: int,
        retry_sleep: float,
        thread_limit: int,
        cache_dir: str,
    ) -> None:
        super().__init__(
            source_lang=source_lang,
            target_lang=target_lang,
            max_retries=max_retries,
            retry_sleep=retry_sleep,
            thread_limit=thread_limit,
            cache_dir=cache_dir,
        )
        self.api_key = get_env_value(api_key_env)
        self.folder_id = folder_id or get_env_value(folder_id_env)
        self.base_url = base_url
        self.timeout_seconds = float(timeout_seconds)
        self.speller = bool(speller)

    def cache_identity(self) -> str:
        return f"{self.folder_id}:{self.speller}:{self.base_url}"

    def validate_text(self, text: str) -> str:
        return "Yandex text limit exceeded" if len(text) > 10_000 else ""

    def translate_sync(self, text: str) -> str:
        payload: dict[str, object] = {
            "folderId": self.folder_id,
            "texts": [text],
            "targetLanguageCode": self.target_lang,
            "speller": self.speller,
        }
        if self.source_lang:
            payload["sourceLanguageCode"] = self.source_lang
        response = httpx.post(
            self.base_url,
            json=payload,
            headers={
                "Authorization": f"Api-Key {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        translations = data.get("translations")
        if not isinstance(translations, list) or not translations:
            raise RuntimeError("Yandex response missing translations")
        translated = translations[0].get("text")
        if not isinstance(translated, str):
            raise RuntimeError("Yandex response missing translated text")
        return translated
