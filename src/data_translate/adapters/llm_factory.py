from collections.abc import Callable

from data_translate.adapters.llm_base import LLMChatAdapter
from data_translate.adapters.litellm_adapter import LiteLLMAdapter
from data_translate.config.models_runtime import LLMRunPolicyModel, LLMSettingsModel


LLMAdapterBuilder = Callable[[LLMRunPolicyModel, LLMSettingsModel], LLMChatAdapter]



def _build_litellm_adapter(runtime: LLMRunPolicyModel, llm: LLMSettingsModel) -> LLMChatAdapter:
    return LiteLLMAdapter(
        provider=llm.provider,
        api_key_env=llm.api_key_env,
        base_url=llm.base_url,
        max_retries=runtime.max_retries,
        retry_sleep=runtime.retry_sleep,
        requests_per_minute=runtime.requests_per_minute,
        site_url=llm.site_url,
        app_name=llm.app_name,
        extra_headers=llm.extra_headers,
    )


PROVIDER_BUILDERS: dict[str, LLMAdapterBuilder] = {
    "openai": _build_litellm_adapter,
    "openrouter": _build_litellm_adapter,
}
DEFAULT_BUILDER: LLMAdapterBuilder = _build_litellm_adapter



def build_llm_chat_adapter(runtime: LLMRunPolicyModel, llm: LLMSettingsModel) -> LLMChatAdapter:
    builder = PROVIDER_BUILDERS.get(llm.provider, DEFAULT_BUILDER)
    return builder(runtime, llm)
