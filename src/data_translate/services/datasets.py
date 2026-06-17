import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from datasets import Dataset, DatasetDict, load_dataset, load_from_disk

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

    def _load_hf_source(self, source: SourceSpecModel, *, max_rows_per_split: int = 0) -> DatasetDict:
        kwargs = {"path": source.hf_dataset_id}
        if source.hf_config:
            kwargs["name"] = source.hf_config
        if source.hf_revision:
            kwargs["revision"] = source.hf_revision
        if source.trust_remote_code:
            kwargs["trust_remote_code"] = True
        try:
            return load_dataset(**kwargs)
        except RuntimeError as exc:
            if "Dataset scripts are no longer supported" not in str(exc):
                raise
            return self._load_hf_source_from_viewer(source, max_rows_per_split=max_rows_per_split)

    def _viewer_json(self, endpoint: str, params: dict[str, str | int]) -> dict:
        url = f"https://datasets-server.huggingface.co/{endpoint}?{urlencode(params)}"
        headers = {"User-Agent": "data-translate"}
        token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with urlopen(Request(url, headers=headers), timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"Hugging Face Dataset Viewer error for {url}: {payload['error']}")
        return payload

    def _load_hf_source_from_viewer(self, source: SourceSpecModel, *, max_rows_per_split: int = 0) -> DatasetDict:
        split_payload = self._viewer_json(
            "splits",
            {
                "dataset": source.hf_dataset_id,
                **({"revision": source.hf_revision} if source.hf_revision else {}),
            },
        )
        split_rows = list(split_payload.get("splits") or [])
        if not split_rows:
            raise RuntimeError(f"Hugging Face Dataset Viewer returned no splits for {source.hf_dataset_id}")
        config = source.hf_config
        if not config:
            configs = sorted({str(item.get("config", "")) for item in split_rows if item.get("config")})
            if len(configs) != 1:
                raise RuntimeError(
                    f"{source.hf_dataset_id} has multiple configs in Dataset Viewer; set source.hf_config explicitly"
                )
            config = configs[0]

        datasets: dict[str, Dataset] = {}
        for split_item in split_rows:
            if str(split_item.get("config", "")) != config:
                continue
            split = str(split_item["split"])
            rows: list[dict] = []
            offset = 0
            total = None
            row_limit = max_rows_per_split if max_rows_per_split > 0 else None
            while total is None or offset < total:
                if row_limit is not None and len(rows) >= row_limit:
                    break
                page_length = 100 if row_limit is None else min(100, row_limit - len(rows))
                payload = self._viewer_json(
                    "rows",
                    {
                        "dataset": source.hf_dataset_id,
                        "config": config,
                        "split": split,
                        "offset": offset,
                        "length": page_length,
                        **({"revision": source.hf_revision} if source.hf_revision else {}),
                    },
                )
                page_rows = [dict(item["row"]) for item in payload.get("rows", [])]
                rows.extend(page_rows)
                total = int(payload.get("num_rows_total") or len(rows))
                if not page_rows:
                    break
                offset += len(page_rows)
            datasets[split] = Dataset.from_list(rows)
        return DatasetDict(datasets)

    def load_source(self, source: SourceSpecModel, *, max_rows_per_split: int = 0) -> DatasetDict:
        disk_path = self.resolve_source_path(source)
        prefer_hf = source.source_kind == "hf" or (
            source.source_kind == "auto" and bool(source.hf_dataset_id) and not source.prefer_local
        )

        if prefer_hf:
            return self._load_hf_source(source, max_rows_per_split=max_rows_per_split)
        if source.source_kind == "disk":
            if disk_path is None:
                raise FileNotFoundError(f"source disk_path not found: {source.disk_path}")
            return load_from_disk(str(disk_path))
        if disk_path is not None:
            return load_from_disk(str(disk_path))
        if source.hf_dataset_id:
            return self._load_hf_source(source, max_rows_per_split=max_rows_per_split)
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


def load_source_dataset(source: SourceSpecModel, *, max_rows_per_split: int = 0) -> DatasetDict:
    return DATASET_RESOLVER.load_source(source, max_rows_per_split=max_rows_per_split)


def dataset_fingerprints(dataset: DatasetDict) -> dict[str, str]:
    return {
        split: str(getattr(split_dataset, "_fingerprint", ""))
        for split, split_dataset in dataset.items()
    }
