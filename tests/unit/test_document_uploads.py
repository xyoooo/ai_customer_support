from datetime import UTC, datetime, timedelta

import pytest

from packages.documents.service import sanitize_filename, validate_media_type
from packages.domain.errors import UploadRejectedError
from packages.storage.local import LocalObjectStore


def test_filename_sanitization_removes_paths_and_controls() -> None:
    assert sanitize_filename("../../customer\x00-guide.md") == "customer-guide.md"
    assert sanitize_filename("..\\..\\billing guide.md") == "billing guide.md"
    assert sanitize_filename("   ") == "upload"


def test_media_validation_requires_extension_type_and_signature_agreement() -> None:
    assert validate_media_type("guide.pdf", "application/pdf", b"%PDF-1.7\n") == "application/pdf"
    assert validate_media_type("guide.md", "text/markdown", b"# Guide\n") == "text/markdown"
    assert validate_media_type("guide.html", "text/html", b"<!doctype html>") == "text/html"

    with pytest.raises(UploadRejectedError):
        validate_media_type("guide.pdf", "application/pdf", b"not a pdf")
    with pytest.raises(UploadRejectedError):
        validate_media_type("guide.md", "application/pdf", b"# Guide\n")
    with pytest.raises(UploadRejectedError):
        validate_media_type("guide.txt", "text/plain", b"binary\x00data")


@pytest.mark.asyncio
async def test_local_object_store_write_move_read_delete_and_reconcile(tmp_path) -> None:
    store = LocalObjectStore(tmp_path)

    async def chunks():  # type: ignore[no-untyped-def]
        yield b"hello "
        yield b"world"

    staged = await store.write("staging/example", chunks())
    assert staged.byte_size == 11
    moved = await store.move("staging/example", "workspaces/a/document.txt")
    assert moved.byte_size == 11
    assert b"".join([chunk async for chunk in store.read(moved.key)]) == b"hello world"
    await store.delete(moved.key)
    with pytest.raises(FileNotFoundError):
        await store.stat(moved.key)

    await store.write("staging/stale", chunks())
    deleted = await store.delete_stale_staging(older_than=datetime.now(UTC) + timedelta(seconds=1))
    assert deleted == 1
