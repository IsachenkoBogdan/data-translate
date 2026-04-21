from pydantic import BaseModel, ConfigDict, Field, model_validator


class BenchmarkSpecModel(BaseModel):
    dataset: str = Field(min_length=1)
    dataset_config: str = Field(min_length=1)
    split: str = Field(min_length=1)
    models: list[str] = Field(min_length=1)
    language_pairs: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    years: list[int | str] = Field(default_factory=list)
    sample_size_per_language_pair: int = Field(ge=0)
    sample_size_total: int = Field(ge=0)
    sampling_score_thresholds: list[float] = Field(default_factory=list)
    seed: int
    source_column: str = Field(min_length=1)
    translation_column: str = Field(min_length=1)
    reference_column: str = ""
    human_score_column: str = Field(min_length=1)
    language_pair_column: str = Field(min_length=1)
    domain_column: str = ""
    year_column: str = ""
    system_column: str = ""
    human_score_min: float
    human_score_max: float
    human_higher_is_better: bool
    bin_labels: list[str] = Field(min_length=1)
    bin_thresholds: list[float] = Field(default_factory=list)
    max_source_chars: int = Field(ge=0)
    max_translation_chars: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_bins(self) -> "BenchmarkSpecModel":
        if len(self.bin_labels) != len(self.bin_thresholds) + 1:
            raise ValueError("bin_labels must contain len(bin_thresholds) + 1 items")
        if self.sampling_score_thresholds != sorted(float(item) for item in self.sampling_score_thresholds):
            raise ValueError("sampling_score_thresholds must be sorted in ascending order")
        return self
