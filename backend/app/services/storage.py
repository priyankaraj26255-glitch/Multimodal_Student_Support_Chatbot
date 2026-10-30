import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from ..config import get_settings

settings = get_settings()
MB = 1024 * 1024


async def read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in chunks, aborting as soon as the size limit is exceeded."""
    chunks, total = [], 0
    while True:
        chunk = await upload.read(MB)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, f"File too large. The maximum allowed size is {max_bytes // MB} MB.")
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(400, "The uploaded file is empty.")
    return b"".join(chunks)


def safe_filename(name: str | None) -> str:
    """Display-only name. Stored files always get random server-generated names."""
    name = os.path.basename((name or "file").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f<>:\"|?*]", "_", name).strip(". ") or "file"
    return name[:200]


def store_bytes(user_id: int, data: bytes, ext: str) -> str:
    folder = Path(settings.upload_dir) / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return str(path)


def read_stored(path: str) -> bytes:
    return Path(path).read_bytes()


def delete_stored(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
