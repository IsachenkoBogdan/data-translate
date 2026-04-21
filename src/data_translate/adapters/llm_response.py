from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    content: str
    attempts: int
    error: str
    usage: dict[str, Any]
    cost: float | None
    finish_reason: str
    rate_limit_waits: int
    rate_limit_wait_seconds: float


def response_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dict(dumped)
    return {}


def extract_usage(response: Any) -> tuple[dict[str, Any], float | None]:
    payload = response_to_dict(response)
    usage = response_to_dict(payload.get("usage"))
    if not usage:
        usage = response_to_dict(getattr(response, "usage", None))
    cost_candidates = [
        payload.get("cost"),
        payload.get("total_cost"),
        usage.get("cost"),
        usage.get("total_cost"),
        usage.get("estimated_cost"),
    ]
    cost = next((float(value) for value in cost_candidates if isinstance(value, int | float)), None)
    return usage, cost


def extract_finish_reason(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        finish_reason = getattr(choices[0], "finish_reason", None)
        if isinstance(finish_reason, str):
            return finish_reason
    payload = response_to_dict(response)
    payload_choices = payload.get("choices")
    if isinstance(payload_choices, list) and payload_choices:
        finish_reason = payload_choices[0].get("finish_reason")
        if isinstance(finish_reason, str):
            return finish_reason
    return ""


def error_response(
    *,
    attempts: int,
    error: str,
    rate_limit_waits: int,
    rate_limit_wait_seconds: float,
) -> LLMResponse:
    return LLMResponse(
        content="",
        attempts=attempts,
        error=error,
        usage={},
        cost=None,
        finish_reason="",
        rate_limit_waits=rate_limit_waits,
        rate_limit_wait_seconds=round(rate_limit_wait_seconds, 4),
    )


def success_response(
    *,
    content: str,
    attempts: int,
    usage: dict[str, Any],
    cost: float | None,
    finish_reason: str,
    rate_limit_waits: int,
    rate_limit_wait_seconds: float,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        attempts=attempts,
        error="",
        usage=usage,
        cost=cost,
        finish_reason=finish_reason,
        rate_limit_waits=rate_limit_waits,
        rate_limit_wait_seconds=round(rate_limit_wait_seconds, 4),
    )
