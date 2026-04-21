from pydantic import BaseModel, ConfigDict, Field

from data_translate.config.models_dataset_evaluation import EvaluationSpecModel
from data_translate.config.models_dataset_reformat import ReformatSpecModel
from data_translate.config.models_dataset_source import ArtifactSpecModel, SourceSpecModel
from data_translate.config.models_dataset_translation import TranslationSpecModel


class DatasetSpecModel(BaseModel):
    dataset_id: str = Field(min_length=1)
    source: SourceSpecModel
    artifacts: ArtifactSpecModel
    translation: TranslationSpecModel | None = None
    evaluation: EvaluationSpecModel | None = None
    reformat: ReformatSpecModel | None = None

    model_config = ConfigDict(extra="forbid")
