import httpx

from data_translate.adapters.http_translation_base import BaseCachedHttpTranslationAdapter
from data_translate.config.settings import get_env_value


class DeepLTranslateAdapter(BaseCachedHttpTranslationAdapter):
    provider_name = "deepl"

    def __init__(
        self,
        *,
        source_lang: str,
        target_lang: str,
        api_key_env: str,
        base_url: str,
        timeout_seconds: float,
        formality: str,
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
        self.base_url = base_url
        self.timeout_seconds = float(timeout_seconds)
        self.formality = formality.strip()

    def cache_identity(self) -> str:
        return f"{self.base_url}:{self.formality}"

    def validate_text(self, text: str) -> str:
        return "DeepL body limit exceeded" if len(text.encode("utf-8")) > 120_000 else ""

    def translate_sync(self, text: str) -> str:
        payload: dict[str, object] = {
            "text": [text],
            "target_lang": self.target_lang,
        }
        if self.source_lang:
            payload["source_lang"] = self.source_lang
        if self.formality:
            payload["formality"] = self.formality
        response = httpx.post(
            self.base_url,
            json=payload,
            headers={
                "Authorization": f"DeepL-Auth-Key {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        translations = data.get("translations")
        if not isinstance(translations, list) or not translations:
            raise RuntimeError("DeepL response missing translations")
        translated = translations[0].get("text")
        if not isinstance(translated, str):
            raise RuntimeError("DeepL response missing translated text")
        return translated
