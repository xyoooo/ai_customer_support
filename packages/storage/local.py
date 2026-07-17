from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from packages.storage.base import ObjectMetadata


class LocalObjectStore:
    """Filesystem adapter that never exposes absolute paths outside this class."""

    def __init__(self, root: Path, *, read_chunk_bytes: int = 64 * 1024) -> None:
        self.root = root.resolve()
        self.read_chunk_bytes = read_chunk_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or "\\" in key or key.startswith("/"):
            raise ValueError("invalid object key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("object key escapes configured root")
        return path

    @staticmethod
    def _metadata(key: str, path: Path) -> ObjectMetadata:
        stat = path.stat()
        return ObjectMetadata(
            key=key,
            byte_size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )

    async def write(self, key: str, chunks: AsyncIterable[bytes]) -> ObjectMetadata:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        handle = await asyncio.to_thread(path.open, "xb")
        try:
            async for chunk in chunks:
                await asyncio.to_thread(handle.write, chunk)
            await asyncio.to_thread(handle.flush)
        except BaseException:
            await asyncio.to_thread(handle.close)
            await asyncio.to_thread(path.unlink, missing_ok=True)
            raise
        await asyncio.to_thread(handle.close)
        return await asyncio.to_thread(self._metadata, key, path)

    async def read(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        handle = await asyncio.to_thread(path.open, "rb")
        try:
            while chunk := await asyncio.to_thread(handle.read, self.read_chunk_bytes):
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def stat(self, key: str) -> ObjectMetadata:
        path = self._path(key)
        return await asyncio.to_thread(self._metadata, key, path)

    async def move(self, source_key: str, destination_key: str) -> ObjectMetadata:
        source = self._path(source_key)
        destination = self._path(destination_key)
        await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(source.replace, destination)
        return await asyncio.to_thread(self._metadata, destination_key, destination)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)

    async def delete_stale_staging(self, *, older_than: datetime) -> int:
        staging = self._path("staging")
        if not staging.exists():
            return 0
        deleted = 0
        for path in await asyncio.to_thread(lambda: list(staging.rglob("*"))):
            if not path.is_file():
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            if modified < older_than:
                await asyncio.to_thread(path.unlink, missing_ok=True)
                deleted += 1
        return deleted
