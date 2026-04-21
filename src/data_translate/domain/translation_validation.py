from typing import Any

from data_translate.config.models_dataset_translation import TranslationRuleModel
from data_translate.domain.translation_common import rule_options
from data_translate.domain.translation_strategies.registry import INPUT_VALIDATORS, STRATEGIES


def rule_validation_error(rule: TranslationRuleModel, value: Any) -> str:
    if rule.strategy not in STRATEGIES:
        return f"unknown translation strategy: {rule.strategy}"
    validator = INPUT_VALIDATORS.get(rule.strategy)
    if validator is None:
        return ""
    return validator(value, rule_options(rule), field_name=str(rule.source))


def validate_rule_value(rule: TranslationRuleModel, value: Any) -> None:
    error = rule_validation_error(rule, value)
    if error:
        raise ValueError(error)
