import hashlib
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path

import anyio
from diskcache import Cache

from data_translate.adapters.runtime_policy import RetryPolicy, run_with_retry
from data_translate.adapters.translation_base import TranslationResult


class BaseCachedHttpTranslationAdapter(ABC):
    def __init__(
        self,
        *,
        source_lang: str,
        target_lang: str,
        max_retries: int,
        retry_sleep: float,
        thread_limit: int,
        cache_dir: str,
    ) -> None:
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.retry_policy = RetryPolicy(
            max_retries=int(max_retries),
            retry_sleep=float(retry_sleep),
        )
        self._cache = Cache(str(Path(cache_dir)))
        self._thread_limiter = anyio.CapacityLimiter(max(1, int(thread_limit)))

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def cache_identity(self) -> str: ...

    @abstractmethod
    def validate_text(self, text: str) -> str: ...

    @abstractmethod
    def translate_sync(self, text: str) -> str: ...

    def _cache_key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.provider_name}:{self.source_lang}:{self.target_lang}:{self.cache_identity()}:{digest}"

    async def translate(self, text: str, *, use_cache: bool) -> TranslationResult:
        if not text.strip():
            return TranslationResult(text=text, status="empty", attempts=0, error="")

        validation_error = self.validate_text(text)
        if validation_error:
            return TranslationResult(text=None, status="error", attempts=0, error=validation_error)

        cache_key = self._cache_key(text)
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return TranslationResult(**cached)

        outcome = await run_with_retry(
            lambda: anyio.to_thread.run_sync(
                self.translate_sync,
                text,
                limiter=self._thread_limiter,
            ),
            policy=self.retry_policy,
        )
        if outcome.error or outcome.value is None:
            return TranslationResult(text=None, status="error", attempts=outcome.attempts, error=outcome.error)

        result = TranslationResult(text=outcome.value, status="ok", attempts=outcome.attempts, error="")
        if use_cache:
            self._cache.set(cache_key, asdict(result))
        return result

    def close(self) -> None:
        self._cache.close()
