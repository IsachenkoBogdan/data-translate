from typing import Any

from data_translate.domain.reporting_common import float_value, rounded


USAGE_KEYS = (
    "usage_prompt_tokens",
    "usage_completion_tokens",
    "usage_total_tokens",
    "usage_cost",
)


def _present(values: list[float | None]) -> list[float]:
    return [value for value in values if value is not None]


def usage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    prompt_tokens = [float_value(row, "usage_prompt_tokens") for row in rows]
    completion_tokens = [float_value(row, "usage_completion_tokens") for row in rows]
    total_tokens = [float_value(row, "usage_total_tokens") for row in rows]
    costs = [float_value(row, "usage_cost") for row in rows]
    rate_limit_waits = [float_value(row, "rate_limit_waits") for row in rows]
    rate_limit_wait_seconds = [float_value(row, "rate_limit_wait_seconds") for row in rows]

    prompt_present = _present(prompt_tokens)
    completion_present = _present(completion_tokens)
    total_present = _present(total_tokens)
    cost_present = _present(costs)
    wait_present = _present(rate_limit_waits)
    wait_seconds_present = _present(rate_limit_wait_seconds)
    request_count = sum(any(row.get(key) is not None for key in USAGE_KEYS) for row in rows)
    retry_count = sum(max(int(row.get("attempts", 1)) - 1, 0) for row in rows)
    return {
        "request_count": request_count,
        "prompt_tokens": int(sum(prompt_present)) if prompt_present else 0,
        "completion_tokens": int(sum(completion_present)) if completion_present else 0,
        "total_tokens": int(sum(total_present)) if total_present else 0,
        "cost": rounded(sum(cost_present)) if cost_present else None,
        "mean_total_tokens_per_request": rounded(sum(total_present) / request_count) if request_count and total_present else None,
        "mean_cost_per_request": rounded(sum(cost_present) / request_count) if request_count and cost_present else None,
        "retry_count": retry_count,
        "rate_limit_waits": int(sum(wait_present)) if wait_present else 0,
        "rate_limit_wait_seconds": rounded(sum(wait_seconds_present)) if wait_seconds_present else 0.0,
    }
