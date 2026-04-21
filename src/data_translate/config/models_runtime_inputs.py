from typing import Literal

from pydantic import BaseModel, ConfigDict


class InputDatasetModel(BaseModel):
    kind: Literal["raw", "translated", "path"]
    path: str = ""
    run_name: str = ""

    model_config = ConfigDict(extra="forbid")
