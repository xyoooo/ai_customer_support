from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    byte_size: int
    modified_at: datetime


class ObjectStore(Protocol):
    async def write(self, key: str, chunks: AsyncIterable[bytes]) -> ObjectMetadata: ...

    def read(self, key: str) -> AsyncIterator[bytes]: ...

    async def stat(self, key: str) -> ObjectMetadata: ...

    async def move(self, source_key: str, destination_key: str) -> ObjectMetadata: ...

    async def delete(self, key: str) -> None: ...

    async def delete_stale_staging(self, *, older_than: datetime) -> int: ...
