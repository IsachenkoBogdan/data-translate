from litellm import acompletion, completion_cost

from data_translate.adapters.llm_response import error_response, extract_finish_reason, extract_usage, success_response
from data_translate.adapters.runtime_policy import RateLimiterTracker, RetryPolicy, run_with_retry
from data_translate.config.settings import get_env_value


class LiteLLMAdapter:
    def __init__(
        self,
        *,
        provider: str,
        api_key_env: str,
        base_url: str,
        max_retries: int,
        retry_sleep: float,
        requests_per_minute: int,
        site_url: str = "",
        app_name: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.provider = provider
        self.api_key = get_env_value(api_key_env)
        self.base_url = base_url
        self.retry_policy = RetryPolicy(
            max_retries=int(max_retries),
            retry_sleep=float(retry_sleep),
        )
        self.rate_limiter = RateLimiterTracker(requests_per_minute)
        self.extra_headers = dict(extra_headers or {})
        if site_url:
            self.extra_headers.setdefault("HTTP-Referer", site_url)
        if app_name:
            self.extra_headers.setdefault("X-Title", app_name)

    def _resolved_model(self, model: str) -> str:
        return model if "/" in model else f"{self.provider}/{model}"

    async def chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ):
        wait_count_before = self.rate_limiter.wait_count
        wait_seconds_before = self.rate_limiter.wait_seconds
        resolved_model = self._resolved_model(model)

        async def create_completion() -> object:
            return await self.rate_limiter.run(
                lambda: acompletion(
                    model=resolved_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                    api_key=self.api_key,
                    base_url=self.base_url or None,
                    extra_headers=self.extra_headers or None,
                )
            )

        outcome = await run_with_retry(create_completion, policy=self.retry_policy)
        rate_limit_waits = self.rate_limiter.wait_count - wait_count_before
        rate_limit_wait_seconds = self.rate_limiter.wait_seconds - wait_seconds_before
        if outcome.error or outcome.value is None:
            return error_response(
                attempts=outcome.attempts,
                error=outcome.error,
                rate_limit_waits=rate_limit_waits,
                rate_limit_wait_seconds=rate_limit_wait_seconds,
            )

        response = outcome.value
        content = ((response.choices[0].message.content or "") if response.choices else "").strip()
        usage, cost = extract_usage(response)
        if cost is None:
            try:
                cost = float(completion_cost(completion_response=response, model=resolved_model))
            except Exception:
                cost = None
        finish_reason = extract_finish_reason(response)
        return success_response(
            content=content,
            attempts=outcome.attempts,
            usage=usage,
            cost=cost,
            finish_reason=finish_reason,
            rate_limit_waits=rate_limit_waits,
            rate_limit_wait_seconds=rate_limit_wait_seconds,
        )

    async def close(self) -> None:
        return None
