from data_translate.domain.translation_strategies.dialog import (
    translate_dialog_turns_content,
    validate_dialog_turns_content_input,
)
from data_translate.domain.translation_strategies.deep_map import (
    translate_deep_map,
    validate_deep_map_input,
)
from data_translate.domain.translation_strategies.nested import (
    translate_nested_text_fields,
    validate_nested_text_fields_input,
)
from data_translate.domain.translation_strategies.serialized import (
    translate_serialized_dialog_turns_content,
    validate_serialized_dialog_turns_content_input,
)
from data_translate.domain.translation_strategies.structured import (
    translate_structured_entity,
    validate_structured_entity_input,
)
from data_translate.domain.translation_strategies.text import (
    translate_text,
    translate_text_list,
    validate_text_input,
    validate_text_list_input,
)
from data_translate.domain.translation_strategies.weblinx import translate_weblinx_query, validate_weblinx_query_input


STRATEGIES = {
    "text": translate_text,
    "text_list": translate_text_list,
    "dialog_turns_content": translate_dialog_turns_content,
    "serialized_dialog_turns_content": translate_serialized_dialog_turns_content,
    "structured_entity": translate_structured_entity,
    "nested_text_fields": translate_nested_text_fields,
    "deep_map_texts": translate_deep_map,
    "weblinx_query": translate_weblinx_query,
}

INPUT_VALIDATORS = {
    "text": validate_text_input,
    "text_list": validate_text_list_input,
    "dialog_turns_content": validate_dialog_turns_content_input,
    "serialized_dialog_turns_content": validate_serialized_dialog_turns_content_input,
    "structured_entity": validate_structured_entity_input,
    "nested_text_fields": validate_nested_text_fields_input,
    "deep_map_texts": validate_deep_map_input,
    "weblinx_query": validate_weblinx_query_input,
}
