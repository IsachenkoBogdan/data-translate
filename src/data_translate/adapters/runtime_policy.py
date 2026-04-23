from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

import anyio
from aiolimiter import AsyncLimiter
from tenacity import AsyncRetrying, RetryError, stop_after_attempt, wait_exponential_jitter, wait_fixed


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int
    retry_sleep: float


@dataclass(frozen=True)
class RetryOutcome(Generic[T]):
    value: T | None
    attempts: int
    error: str


def format_exception(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:300]}"


async def run_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
) -> RetryOutcome[T]:
    attempts = 0
    wait_strategy = (
        wait_fixed(0)
        if float(policy.retry_sleep) <= 0
        else wait_exponential_jitter(
            initial=float(policy.retry_sleep),
            max=max(float(policy.retry_sleep) * 8.0, float(policy.retry_sleep)),
            jitter=float(policy.retry_sleep),
        )
    )
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(int(policy.max_retries) + 1),
            wait=wait_strategy,
            reraise=False,
        ):
            with attempt:
                attempts += 1
                return RetryOutcome(
                    value=await operation(),
                    attempts=attempts,
                    error="",
                )
    except RetryError as exc:
        last_exc = exc.last_attempt.exception() if exc.last_attempt else None
        error = str(exc)[:300] if last_exc is None else format_exception(last_exc)
        return RetryOutcome(value=None, attempts=attempts, error=error)
    except Exception as exc:
        return RetryOutcome(value=None, attempts=attempts, error=format_exception(exc))
    return RetryOutcome(value=None, attempts=attempts, error="retry loop finished without result")


class RateLimiterTracker:
    def __init__(self, requests_per_minute: int) -> None:
        self._limiter = AsyncLimiter(max(1, int(requests_per_minute)), 60) if requests_per_minute > 0 else None
        self.wait_count = 0
        self.wait_seconds = 0.0

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        if self._limiter is None:
            return await operation()
        started = anyio.current_time()
        async with self._limiter:
            waited = anyio.current_time() - started
            if waited > 0.01:
                self.wait_count += 1
                self.wait_seconds += waited
            return await operation()
