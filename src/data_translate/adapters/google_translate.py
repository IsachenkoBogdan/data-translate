import hashlib
from dataclasses import asdict
from pathlib import Path
from threading import local

import anyio
from deep_translator.google import (
    BeautifulSoup,
    GoogleTranslator,
    RequestError,
    TooManyRequests,
    TranslationNotFound,
    is_empty,
    is_input_valid,
    request_failed,
    requests as google_requests,
)
from diskcache import Cache

from data_translate.adapters.runtime_policy import RetryPolicy, run_with_retry
from data_translate.adapters.translation_base import TranslationResult


class _TimeoutGoogleTranslator(GoogleTranslator):
    def __init__(self, *, timeout_seconds: float, **kwargs) -> None:
        self.timeout_seconds = float(timeout_seconds)
        super().__init__(**kwargs)

    def translate(self, text: str, **kwargs) -> str:
        del kwargs
        if is_input_valid(text, max_chars=5000):
            text = text.strip()
            if self._same_source_target() or is_empty(text):
                return text
            self._url_params["tl"] = self._target
            self._url_params["sl"] = self._source
            if self.payload_key:
                self._url_params[self.payload_key] = text

            response = google_requests.get(
                self._base_url,
                params=self._url_params,
                proxies=self.proxies,
                timeout=self.timeout_seconds,
            )
            try:
                if response.status_code == 429:
                    raise TooManyRequests()
                if request_failed(status_code=response.status_code):
                    raise RequestError()

                soup = BeautifulSoup(response.text, "html.parser")
                element = soup.find(self._element_tag, self._element_query)
                if not element:
                    element = soup.find(self._element_tag, self._alt_element_query)
                    if not element:
                        raise TranslationNotFound(text)
                if element.get_text(strip=True) == text.strip():
                    to_translate_alpha = "".join(ch for ch in text.strip() if ch.isalnum())
                    translated_alpha = "".join(ch for ch in element.get_text(strip=True) if ch.isalnum())
                    if to_translate_alpha and translated_alpha and to_translate_alpha == translated_alpha:
                        self._url_params["tl"] = self._target
                        if "hl" not in self._url_params:
                            return text.strip()
                        del self._url_params["hl"]
                        return self.translate(text)
                return element.get_text(strip=True)
            finally:
                response.close()
        return text


class GoogleTranslateAdapter:
    def __init__(
        self,
        *,
        source_lang: str,
        target_lang: str,
        timeout_seconds: float,
        max_retries: int,
        retry_sleep: float,
        thread_limit: int,
        cache_dir: str,
    ) -> None:
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.timeout_seconds = float(timeout_seconds)
        self.retry_policy = RetryPolicy(
            max_retries=int(max_retries),
            retry_sleep=float(retry_sleep),
        )
        self._local = local()
        self._cache = Cache(str(Path(cache_dir)))
        self._thread_limiter = anyio.CapacityLimiter(max(1, int(thread_limit)))

    def _translator(self) -> GoogleTranslator:
        translator = getattr(self._local, "translator", None)
        if translator is None:
            translator = _TimeoutGoogleTranslator(
                source=self.source_lang,
                target=self.target_lang,
                timeout_seconds=self.timeout_seconds,
            )
            self._local.translator = translator
        return translator

    def _translate_sync(self, text: str) -> str:
        return self._translator().translate(text)

    def _cache_key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.source_lang}:{self.target_lang}:{digest}"

    async def translate(self, text: str, *, use_cache: bool) -> TranslationResult:
        if not text.strip():
            return TranslationResult(text=text, status="empty", attempts=0, error="")

        cache_key = self._cache_key(text)
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return TranslationResult(**cached)

        outcome = await run_with_retry(
            lambda: anyio.to_thread.run_sync(
                self._translate_sync,
                text,
                limiter=self._thread_limiter,
            ),
            policy=self.retry_policy,
        )
        if outcome.error or outcome.value is None:
            return TranslationResult(
                text=None,
                status="error",
                attempts=outcome.attempts,
                error=outcome.error,
            )

        result = TranslationResult(text=outcome.value, status="ok", attempts=outcome.attempts, error="")
        if use_cache:
            self._cache.set(cache_key, asdict(result))
        return result

    def close(self) -> None:
        self._cache.close()
