import json
import re
from typing import Any

from data_translate.adapters.llm_base import LLMChatAdapter


def clamp_score(value: int | float) -> int:
    return max(0, min(10, int(value)))


def _strip_code_fences(content: str) -> str:
    fenced_match = re.match(r"^```[a-zA-Z0-9_-]*\s*(.*?)\s*```$", content.strip(), re.DOTALL)
    return fenced_match.group(1).strip() if fenced_match else content.strip()


def _first_json_object(content: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    text = _strip_code_fences(content)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    for match in re.finditer(r"\{", text):
        try:
            candidate, _end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


def _json_score_payload(content: str) -> tuple[int | None, str, str]:
    data = _first_json_object(content)
    if data is None:
        return None, "", ""
    score = data.get("score")
    if not isinstance(score, int | float):
        return None, "", ""
    return clamp_score(score), str(data.get("comment", "")), "json"


def _regex_score_payload(content: str) -> tuple[int | None, str, str]:
    score_match = re.search(r"score[\"\s:]+(\d+)", content, re.IGNORECASE)
    if not score_match:
        return None, "", ""
    return clamp_score(int(score_match.group(1))), content[:200], "regex_score"


def parse_score_response(content: str) -> tuple[int | None, str, str]:
    content = _strip_code_fences(content)
    for parser in (_json_score_payload, _regex_score_payload):
        score, comment, parse_status = parser(content)
        if score is not None:
            return score, comment, parse_status
    return None, content[:200], "parse_error"


def _usage_int(usage: dict[str, Any], key: str) -> int | None:
    value = usage.get(key)
    return int(value) if isinstance(value, int | float) else None


def _usage_payload(response: Any) -> dict[str, Any]:
    usage_prompt_tokens = _usage_int(response.usage, "prompt_tokens")
    usage_completion_tokens = _usage_int(response.usage, "completion_tokens")
    usage_total_tokens = _usage_int(response.usage, "total_tokens")
    if usage_total_tokens is None and usage_prompt_tokens is not None and usage_completion_tokens is not None:
        usage_total_tokens = usage_prompt_tokens + usage_completion_tokens
    return {
        "usage": response.usage,
        "usage_prompt_tokens": usage_prompt_tokens,
        "usage_completion_tokens": usage_completion_tokens,
        "usage_total_tokens": usage_total_tokens,
        "usage_cost": response.cost,
        "finish_reason": response.finish_reason,
        "rate_limit_waits": response.rate_limit_waits,
        "rate_limit_wait_seconds": response.rate_limit_wait_seconds,
    }


def _error_result(*, score_key: str, response: Any, usage_data: dict[str, Any]) -> dict[str, Any]:
    return {
        score_key: None,
        "comment": "",
        "status": "error",
        "parse_status": "request_error",
        "raw_response": "",
        "attempts": response.attempts,
        "error": response.error,
        **usage_data,
    }


def _parsed_result(
    *,
    score_key: str,
    raw: str,
    attempts: int,
    usage_data: dict[str, Any],
) -> dict[str, Any]:
    score, comment, parse_status = parse_score_response(raw)
    status = "ok" if score is not None else "parse_error"
    return {
        score_key: score,
        "comment": comment,
        "status": status,
        "parse_status": parse_status,
        "raw_response": raw,
        "attempts": attempts,
        "error": "" if status == "ok" else "could not parse score",
        **usage_data,
    }


class TranslationJudge:
    def __init__(
        self,
        *,
        adapter: LLMChatAdapter,
        model: str,
        system_prompt: str,
        prompt_template: str,
        max_completion_tokens: int,
        temperature: float,
    ) -> None:
        self.adapter = adapter
        self.model = model
        self.system_prompt = system_prompt
        self.prompt_template = prompt_template
        self.max_completion_tokens = int(max_completion_tokens)
        self.temperature = float(temperature)

    async def score(
        self,
        *,
        source_text: str,
        translation_text: str,
        source_lang: str,
        target_lang: str,
        domain: str,
        reference_text: str = "",
        score_key: str = "score",
    ) -> dict[str, Any]:
        prompt = self.prompt_template.format(
            source_lang=source_lang,
            target_lang=target_lang,
            domain=domain,
            source_text=source_text,
            translation=translation_text,
            reference_text=reference_text,
        )
        response = await self.adapter.chat(
            model=self.model,
            system_prompt=self.system_prompt,
            user_prompt=prompt,
            temperature=self.temperature,
            max_tokens=self.max_completion_tokens,
        )
        usage_data = _usage_payload(response)
        if response.error:
            return _error_result(score_key=score_key, response=response, usage_data=usage_data)

        raw = response.content.strip()
        return _parsed_result(
            score_key=score_key,
            raw=raw,
            attempts=response.attempts,
            usage_data=usage_data,
        )
