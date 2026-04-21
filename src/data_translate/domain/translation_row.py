from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.config.models_dataset_translation import TranslationRuleModel
from data_translate.domain.translation_common import StrategyResult, rule_options
from data_translate.domain.translation_strategies import STRATEGIES
from data_translate.domain.translation_validation import validate_rule_value


async def translate_by_rule(rule: TranslationRuleModel, row: dict[str, Any], adapter: TranslationAdapter) -> StrategyResult:
    if rule.strategy not in STRATEGIES:
        raise ValueError(f"unknown translation strategy: {rule.strategy}")
    validate_rule_value(rule, row.get(rule.source))
    strategy = STRATEGIES[rule.strategy]
    return await strategy(row.get(rule.source), adapter, rule_options(rule), use_cache=rule.cache)


async def translate_row(row_idx: int, row: dict[str, Any], rules: list[TranslationRuleModel], adapter: TranslationAdapter) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    errors: list[str] = []
    attempts = 0
    for rule in rules:
        target = str(rule.target or rule.source)
        result = await translate_by_rule(rule, row, adapter)
        outputs[target] = result.value
        attempts += result.attempts
        if result.error:
            errors.append(f"{target}: {result.error}")
    return {
        "row_idx": row_idx,
        **outputs,
        "status": "error" if errors else "ok",
        "error": "; ".join(errors),
        "attempts": attempts,
    }
