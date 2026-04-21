from data_translate.adapters.llm_base import LLMChatAdapter
from data_translate.adapters.llm_factory import build_llm_chat_adapter
from data_translate.config.loader import load_text
from data_translate.config.models_runtime import LLMRunPolicyModel, LLMSettingsModel, PromptSettingsModel
from data_translate.domain.judging import TranslationJudge


def build_llm_adapter(runtime: LLMRunPolicyModel, llm: LLMSettingsModel) -> LLMChatAdapter:
    return build_llm_chat_adapter(runtime, llm)


def build_translation_judge(
    *,
    adapter: LLMChatAdapter,
    runtime: LLMRunPolicyModel,
    llm: LLMSettingsModel,
    prompt: PromptSettingsModel,
    model: str | None = None,
) -> TranslationJudge:
    return TranslationJudge(
        adapter=adapter,
        model=model or llm.model,
        system_prompt=load_text(prompt.system_prompt_file),
        prompt_template=load_text(prompt.prompt_file),
        max_completion_tokens=runtime.max_completion_tokens,
        temperature=llm.temperature,
    )
