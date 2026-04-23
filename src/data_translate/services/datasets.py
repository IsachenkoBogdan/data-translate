from pathlib import Path

from datasets import DatasetDict, load_dataset, load_from_disk

from data_translate.config.models_dataset_source import SourceSpecModel
from data_translate.config.models_runtime_inputs import InputDatasetModel
from data_translate.config.models_workflow import EvaluateWorkflowConfigModel
from data_translate.domain.languages import language_code
from data_translate.engine.artifacts import build_materialized_output_path


class DatasetResolver:
    def resolve_source_path(self, source: SourceSpecModel) -> Path | None:
        if source.disk_path and Path(source.disk_path).exists():
            return Path(source.disk_path)
        return None

    def _load_hf_source(self, source: SourceSpecModel) -> DatasetDict:
        kwargs = {"path": source.hf_dataset_id}
        if source.hf_config:
            kwargs["name"] = source.hf_config
        if source.trust_remote_code:
            kwargs["trust_remote_code"] = True
        return load_dataset(**kwargs)

    def load_source(self, source: SourceSpecModel) -> DatasetDict:
        disk_path = self.resolve_source_path(source)
        prefer_hf = source.source_kind == "hf" or (
            source.source_kind == "auto" and bool(source.hf_dataset_id) and not source.prefer_local
        )

        if prefer_hf:
            return self._load_hf_source(source)
        if source.source_kind == "disk":
            if disk_path is None:
                raise FileNotFoundError(f"source disk_path not found: {source.disk_path}")
            return load_from_disk(str(disk_path))
        if disk_path is not None:
            return load_from_disk(str(disk_path))
        if source.hf_dataset_id:
            return self._load_hf_source(source)
        raise ValueError("source spec is not readable")

    def resolve_input_path(self, config: EvaluateWorkflowConfigModel, ref: InputDatasetModel) -> Path:
        if ref.kind == "path":
            path = Path(ref.path)
        elif ref.kind == "source":
            raise ValueError("source input kind does not resolve to a local path")
        elif ref.kind == "raw":
            path = config.dataset.artifacts.raw_path or config.dataset.source.disk_path
            if not path:
                raise ValueError("raw input path is not configured")
            path = Path(path)
        elif ref.kind == "translated":
            if ref.path.strip():
                path = Path(ref.path)
            else:
                evaluation = config.dataset.evaluation
                if evaluation is None:
                    raise ValueError("evaluate workflow requires dataset.evaluation")
                translated_basename = config.dataset.artifacts.translated_basename
                target_lang = language_code(evaluation.target_lang)
                run_name = ref.run_name or config.meta.run_name
                resolved = build_materialized_output_path(
                    translated_basename=translated_basename,
                    target_lang=target_lang,
                    run_name=run_name,
                )
                if resolved is None:
                    raise ValueError("translated input path is not configured")
                path = resolved
        else:
            raise ValueError(f"unknown input dataset kind: {ref.kind}")
        if not path.exists():
            raise FileNotFoundError(f"input dataset path not found: {path}")
        return path

    def resolve_evaluation_input_paths(self, config: EvaluateWorkflowConfigModel) -> dict[str, Path | None]:
        evaluation = config.dataset.evaluation
        if evaluation is None:
            raise ValueError("evaluate workflow requires dataset.evaluation")
        return {
            alias: (None if ref.kind == "source" else self.resolve_input_path(config, ref))
            for alias, ref in evaluation.inputs.items()
        }

    def load_evaluation_inputs(self, config: EvaluateWorkflowConfigModel) -> dict[str, DatasetDict]:
        return self.load_evaluation_inputs_from_paths(config, self.resolve_evaluation_input_paths(config))

    def load_evaluation_inputs_from_paths(
        self,
        config: EvaluateWorkflowConfigModel,
        input_paths: dict[str, Path | None],
    ) -> dict[str, DatasetDict]:
        evaluation = config.dataset.evaluation
        if evaluation is None:
            raise ValueError("evaluate workflow requires dataset.evaluation")
        datasets: dict[str, DatasetDict] = {}
        for alias, path in input_paths.items():
            ref = evaluation.inputs[alias]
            if ref.kind == "source":
                datasets[alias] = self.load_source(config.dataset.source)
            else:
                if path is None:
                    raise ValueError(f"input path is not configured for alias {alias!r}")
                datasets[alias] = load_from_disk(str(path))
        return datasets


DATASET_RESOLVER = DatasetResolver()


def load_source_dataset(source: SourceSpecModel) -> DatasetDict:
    return DATASET_RESOLVER.load_source(source)


def dataset_fingerprints(dataset: DatasetDict) -> dict[str, str]:
    return {
        split: str(getattr(split_dataset, "_fingerprint", ""))
        for split, split_dataset in dataset.items()
    }
