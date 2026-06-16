from contextlib import AbstractContextManager, nullcontext
import sys
from typing import Protocol

from tqdm import tqdm


class Progress(Protocol):
    def update(self, n: int = 1) -> object: ...

    def close(self) -> object: ...


class NoopProgress:
    def update(self, n: int = 1) -> None:
        return None

    def close(self) -> None:
        return None


def progress_bar(*, total: int, desc: str, unit: str, enabled: bool = True) -> AbstractContextManager[Progress]:
    if not enabled or total <= 0 or not sys.stderr.isatty():
        return nullcontext(NoopProgress())
    return tqdm(total=total, desc=desc, unit=unit)
