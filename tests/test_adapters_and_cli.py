from types import SimpleNamespace
from unittest.mock import Mock, patch

import anyio
import pytest

from data_translate.adapters.deepl_translate import DeepLTranslateAdapter
from data_translate.adapters.google_translate import GoogleTranslateAdapter
from data_translate.adapters.http_translation_base import BaseCachedHttpTranslationAdapter
from data_translate.adapters.litellm_adapter import LiteLLMAdapter
from data_translate.adapters.llm_factory import build_llm_chat_adapter
from data_translate.adapters.llm_response import LLMResponse
from data_translate.adapters.runtime_policy import RateLimiterTracker, RetryOutcome, RetryPolicy, format_exception, run_with_retry
from data_translate.adapters.translation_base import TranslationResult
from data_translate.adapters.translation_factory import build_translation_adapter
from data_translate.adapters.yandex_translate import YandexTranslateAdapter
from data_translate.cli.main import main as cli_main
from data_translate.cli.parser import build_parser
from data_translate.cli.registry import run_workflow
from data_translate.config.loader import load_workflow_model
from data_translate.config.models_dataset_translation import (
    DeepLTranslationBackendModel,
    GoogleTranslationBackendModel,
    YandexTranslationBackendModel,
)
from data_translate.config.settings import EnvironmentSettings, get_env_value
from data_translate.domain.renderers import render_value


class DummyHttpAdapter(BaseCachedHttpTranslationAdapter):
    provider_name = "dummy"

    def cache_identity(self) -> str:
        return "v1"

    def validate_text(self, text: str) -> str:
        return "bad text" if text == "bad" else ""

    def translate_sync(self, text: str) -> str:
        return f"tr:{text}"


def test_runtime_policy_and_rate_limiter() -> None:
    assert "RuntimeError" in format_exception(RuntimeError("boom"))

    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("retry")
        return "ok"

    async def run_success():
        return await run_with_retry(flaky, policy=RetryPolicy(max_retries=2, retry_sleep=0))

    outcome = anyio.run(run_success)
    assert outcome.value == "ok"
    assert outcome.attempts == 2

    async def always_fail() -> None:
        raise RuntimeError("fail")

    async def run_error():
        return await run_with_retry(always_fail, policy=RetryPolicy(max_retries=1, retry_sleep=0))

    error_outcome = anyio.run(run_error)
    assert error_outcome.value is None
    assert "RuntimeError" in error_outcome.error

    tracker = RateLimiterTracker(0)

    async def done() -> str:
        return "done"

    async def run_tracker():
        return await tracker.run(done)

    assert anyio.run(run_tracker) == "done"


def test_rate_limiter_tracker_counts_waits_when_limiter_blocks() -> None:
    tracker = RateLimiterTracker(1)

    class SlowLimiter:
        async def __aenter__(self):
            await anyio.sleep(0.02)
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    tracker._limiter = SlowLimiter()

    async def done() -> str:
        return "done"

    async def run_tracker():
        return await tracker.run(done)

    assert anyio.run(run_tracker) == "done"
    assert tracker.wait_count == 1
    assert tracker.wait_seconds > 0.01


def test_base_http_adapter_translate_and_cache(tmp_path) -> None:
    adapter = DummyHttpAdapter(
        source_lang="en",
        target_lang="fr",
        max_retries=1,
        retry_sleep=0,
        thread_limit=1,
        cache_dir=str(tmp_path / "cache"),
    )

    async def run():
        empty = await adapter.translate(" ", use_cache=True)
        invalid = await adapter.translate("bad", use_cache=True)
        first = await adapter.translate("hello", use_cache=True)
        second = await adapter.translate("hello", use_cache=True)
        return empty, invalid, first, second

    empty, invalid, first, second = anyio.run(run)
    assert empty.status == "empty"
    assert invalid.error == "bad text"
    assert first.text == "tr:hello"
    assert second.text == "tr:hello"
    adapter.close()


def test_provider_adapters_and_factories(tmp_path) -> None:
    with patch("data_translate.adapters.deepl_translate.get_env_value", return_value="key"):
        deepl = DeepLTranslateAdapter(
            source_lang="EN",
            target_lang="FR",
            api_key_env="DEEPL_API_KEY",
            base_url="https://deepl",
            timeout_seconds=1.0,
            formality=" prefer_more ",
            max_retries=1,
            retry_sleep=0,
            thread_limit=1,
            cache_dir=str(tmp_path / "d"),
        )
    assert deepl.cache_identity() == "https://deepl:prefer_more"
    assert deepl.validate_text("x" * 120001) == "DeepL body limit exceeded"

    with patch("data_translate.adapters.deepl_translate.httpx.post") as post_mock:
        response = Mock()
        response.json.return_value = {"translations": [{"text": "bonjour"}]}
        response.raise_for_status.return_value = None
        post_mock.return_value = response
        assert deepl.translate_sync("hello") == "bonjour"
    deepl.close()

    with patch("data_translate.adapters.yandex_translate.get_env_value", side_effect=["key", "folder"]):
        yandex = YandexTranslateAdapter(
            source_lang="en",
            target_lang="fr",
            api_key_env="YANDEX_API_KEY",
            folder_id="",
            folder_id_env="YANDEX_FOLDER_ID",
            base_url="https://yandex",
            timeout_seconds=1.0,
            speller=True,
            max_retries=1,
            retry_sleep=0,
            thread_limit=1,
            cache_dir=str(tmp_path / "y"),
        )
    assert yandex.cache_identity() == "folder:True:https://yandex"
    assert yandex.validate_text("x" * 10001) == "Yandex text limit exceeded"

    with patch("data_translate.adapters.yandex_translate.httpx.post") as post_mock:
        response = Mock()
        response.json.return_value = {"translations": [{"text": "bonjour"}]}
        response.raise_for_status.return_value = None
        post_mock.return_value = response
        assert yandex.translate_sync("hello") == "bonjour"
    yandex.close()

    google = GoogleTranslateAdapter(
        source_lang="en",
        target_lang="fr",
        timeout_seconds=1.0,
        max_retries=1,
        retry_sleep=0,
        thread_limit=1,
        cache_dir=str(tmp_path / "g"),
    )
    with patch.object(google, "_translate_sync", return_value="bonjour"):
        async def run():
            return await google.translate("hello", use_cache=True)
        result = anyio.run(run)
    assert result.text == "bonjour"
    google.close()

    google_timeout = GoogleTranslateAdapter(
        source_lang="en",
        target_lang="fr",
        timeout_seconds=7.0,
        max_retries=1,
        retry_sleep=0,
        thread_limit=1,
        cache_dir=str(tmp_path / "g-timeout"),
    )
    with patch("data_translate.adapters.google_translate.google_requests.get") as get_mock:
        response = Mock()
        response.status_code = 200
        response.text = '<div class="t0">bonjour</div>'
        response.close.return_value = None
        get_mock.return_value = response
        assert google_timeout._translate_sync("hello") == "bonjour"
        assert get_mock.call_args.kwargs["timeout"] == 7.0
    google_timeout.close()

    runtime = load_workflow_model("translate", dataset_id="faithdial").runtime
    with patch("data_translate.adapters.translation_factory.GoogleTranslateAdapter", return_value="google") as google_builder:
        assert build_translation_adapter(
            source_lang="English",
            target_lang="French",
            runtime=runtime,
            backend=GoogleTranslationBackendModel(),
            cache_dir="cache",
        ) == "google"
        google_builder.assert_called_once()
        assert google_builder.call_args.kwargs["timeout_seconds"] == 5.0
    with patch("data_translate.adapters.translation_factory.DeepLTranslateAdapter", return_value="deepl"):
        assert build_translation_adapter(
            source_lang="English",
            target_lang="French",
            runtime=runtime,
            backend=DeepLTranslationBackendModel(api_key_env="DEEPL_API_KEY"),
            cache_dir="cache",
        ) == "deepl"
    with patch("data_translate.adapters.translation_factory.YandexTranslateAdapter", return_value="yandex"):
        assert build_translation_adapter(
            source_lang="English",
            target_lang="French",
            runtime=runtime,
            backend=YandexTranslationBackendModel(api_key_env="YANDEX_API_KEY", folder_id="folder"),
            cache_dir="cache",
        ) == "yandex"
    with pytest.raises(ValueError):
        build_translation_adapter(
            source_lang="en",
            target_lang="fr",
            runtime=runtime,
            backend=object(),
            cache_dir="cache",
        )


def test_litellm_adapter_and_factories() -> None:
    with patch("data_translate.adapters.litellm_adapter.get_env_value", return_value="key"):
        adapter = LiteLLMAdapter(
            provider="openrouter",
            api_key_env="OPENROUTER_API_KEY",
            base_url="https://openrouter",
            max_retries=1,
            retry_sleep=0,
            requests_per_minute=0,
            site_url="https://site",
            app_name="Data Translate",
        )
    assert adapter._resolved_model("gpt-4o-mini") == "openrouter/gpt-4o-mini"

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=" hello "), finish_reason="stop")],
        usage={"prompt_tokens": 2, "completion_tokens": 3},
    )
    with (
        patch("data_translate.adapters.litellm_adapter.run_with_retry", return_value=RetryOutcome(value=response, attempts=1, error="")),
        patch("data_translate.adapters.litellm_adapter.completion_cost", return_value=0.2),
    ):
        async def run():
            return await adapter.chat(
                model="gpt-4o-mini",
                system_prompt="sys",
                user_prompt="user",
                temperature=0.0,
                max_tokens=10,
            )
        result = anyio.run(run)
    assert result.content == "hello"
    assert result.cost == 0.2

    with patch("data_translate.adapters.litellm_adapter.run_with_retry", return_value=RetryOutcome(value=None, attempts=2, error="boom")):
        async def run_error():
            return await adapter.chat(
                model="gpt-4o-mini",
                system_prompt="sys",
                user_prompt="user",
                temperature=0.0,
                max_tokens=10,
            )
        error_result = anyio.run(run_error)
    assert error_result.error == "boom"

    llm_config = load_workflow_model("evaluate", dataset_id="faithdial").llm
    runtime = load_workflow_model("evaluate", dataset_id="faithdial").runtime
    with patch("data_translate.adapters.llm_factory.LiteLLMAdapter", return_value="adapter") as builder:
        assert build_llm_chat_adapter(runtime, llm_config) == "adapter"
        builder.assert_called_once()


def test_settings_and_cli_entrypoints(monkeypatch, capsys) -> None:
    with patch("data_translate.config.settings.get_environment_settings", return_value=EnvironmentSettings()), patch(
        "os.getenv", return_value="secret"
    ):
        assert get_env_value("OPENAI_API_KEY") == "secret"
    with patch("data_translate.config.settings.get_environment_settings", return_value=EnvironmentSettings()):
        assert get_env_value("OPENAI_API_KEY", required=False) == ""
        with pytest.raises(RuntimeError):
            get_env_value("OPENAI_API_KEY")

    parser = build_parser()
    args = parser.parse_args(["translate", "--dataset", "faithdial"])
    assert args.command == "translate"
    args = parser.parse_args(["check-translation", "--dataset", "faithdial", "--no-progress"])
    assert args.command == "check-translation"
    assert args.dataset == "faithdial"
    assert args.no_progress is True
    args = parser.parse_args(["check-translation-fix", "--dataset", "faithdial", "--max-fixes", "3", "--no-progress"])
    assert args.command == "check-translation-fix"
    assert args.max_fixes == 3
    assert args.no_progress is True
    args = parser.parse_args(["config-show", "--workflow", "translate"])
    assert args.command == "config-show"

    config = load_workflow_model("translate", dataset_id="faithdial")
    with patch("data_translate.cli.registry.get_workflow_definition", return_value=SimpleNamespace(runner=Mock())):
        run_workflow(config)

    with patch("data_translate.cli.main.build_parser") as parser_builder, patch(
        "data_translate.cli.main.load_workflow_model", return_value=config
    ) as load_mock, patch("data_translate.cli.main.run_workflow") as run_mock:
        parser_builder.return_value.parse_args.return_value = SimpleNamespace(
            command="translate",
            config_root="conf",
            dataset="faithdial",
            run="",
            overrides=[],
        )
        cli_main()
    load_mock.assert_called_once()
    run_mock.assert_called_once()

    with patch("data_translate.cli.main.build_parser") as parser_builder, patch(
        "data_translate.cli.main.load_workflow_model", return_value=config
    ):
        parser_builder.return_value.parse_args.return_value = SimpleNamespace(
            command="config-show",
            workflow="translate",
            config_root="conf",
            dataset="faithdial",
            run="",
            overrides=[],
        )
        cli_main()
    assert '"workflow": "translate"' in capsys.readouterr().out

    with patch("data_translate.cli.main.build_parser") as parser_builder, patch(
        "data_translate.cli.main.run_translation_quality_check",
        return_value={"checked_rows": 1, "error_count": 0, "warning_count": 0, "issues": []},
    ) as check_mock:
        parser_builder.return_value.parse_args.return_value = SimpleNamespace(
            command="check-translation",
            config_root="conf",
            dataset="faithdial",
            path="",
            run="",
            overrides=[],
            max_issues=50,
            max_rows_per_split=0,
            no_progress=True,
        )
        cli_main()
    check_mock.assert_called_once()
    assert "check-translation" in capsys.readouterr().out

    with patch("data_translate.cli.main.build_parser") as parser_builder, patch(
        "data_translate.services.translation_quality_fix.run_translation_quality_fix",
        return_value={
            "dataset_id": "faithdial",
            "selected_issue_count": 1,
            "suggestion_count": 1,
            "suggestions_path": "fix_suggestions.jsonl",
            "suggestions_html_path": "fix_suggestions.html",
        },
    ) as fix_mock:
        parser_builder.return_value.parse_args.return_value = SimpleNamespace(
            command="check-translation-fix",
            config_root="conf",
            dataset="faithdial",
            run="",
            overrides=[],
            max_fixes=50,
            no_progress=True,
        )
        cli_main()
    fix_mock.assert_called_once()
    assert "check-translation-fix" in capsys.readouterr().out
