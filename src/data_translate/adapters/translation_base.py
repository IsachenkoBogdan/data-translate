from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranslationResult:
    text: str | None
    status: str
    attempts: int
    error: str


class TranslationAdapter(Protocol):
    async def translate(self, text: str, *, use_cache: bool) -> TranslationResult: ...

    def close(self) -> None: ...
