from __future__ import annotations

import errno
import os
import re
import shutil
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_FILENAME_LENGTH = 220


def sanitize_filename(filename: str | None) -> str:
    """Return a safe, portable filename without directory components."""
    raw_name = (filename or "").replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFKC", raw_name)
    name = _INVALID_FILENAME_CHARS.sub("_", name)
    name = "".join(char for char in name if char.isprintable()).strip(" .")

    if name in {"", ".", ".."}:
        name = "unnamed_file"

    if len(name) > _MAX_FILENAME_LENGTH:
        suffix = Path(name).suffix[:24]
        stem = name[:-len(suffix)] if suffix else name
        name = stem[: _MAX_FILENAME_LENGTH - len(suffix)] + suffix

    return name


def _collision_name(original_name: str) -> str:
    path = Path(original_name)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    unique_part = uuid.uuid4().hex[:8]
    return f"{path.stem}_{timestamp}_{unique_part}{path.suffix}"


def finalize_temp_file(temp_path: Path, files_dir: Path, original_name: str) -> Path:
    """
    Atomically move a completed temporary file into files_dir.

    Existing files are never overwritten. A timestamp and random suffix are
    added only when the requested filename already exists.
    """
    files_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(original_name)

    for attempt in range(20):
        candidate_name = safe_name if attempt == 0 else _collision_name(safe_name)
        destination = files_dir / candidate_name

        try:
            # The temporary file is created inside files_dir, so this hard link
            # is atomic and does not copy the file contents a second time.
            os.link(temp_path, destination)
        except FileExistsError:
            continue
        except OSError as exc:
            if exc.errno not in {
                errno.EPERM,
                errno.EOPNOTSUPP,
                errno.ENOTSUP,
                errno.EXDEV,
            }:
                raise

            # Fallback for filesystems that do not support hard links.
            try:
                descriptor = os.open(
                    destination,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o640,
                )
            except FileExistsError:
                continue

            try:
                with os.fdopen(descriptor, "wb") as output, temp_path.open("rb") as source:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
            except BaseException:
                destination.unlink(missing_ok=True)
                raise

        temp_path.unlink(missing_ok=True)
        return destination

    raise FileExistsError("Could not allocate a unique filename after 20 attempts.")


def copy_local_file(source_path: Path, files_dir: Path, original_name: str) -> Path:
    """Copy a file from the Local Bot API Server shared volume into files_dir."""
    if not source_path.is_file():
        raise FileNotFoundError(
            f"Telegram's local file is not accessible: {source_path}"
        )

    files_dir.mkdir(parents=True, exist_ok=True)
    temp_path = files_dir / f".uploadbot-{uuid.uuid4().hex}.part"

    try:
        shutil.copyfile(source_path, temp_path)
        return finalize_temp_file(temp_path, files_dir, original_name)
    finally:
        temp_path.unlink(missing_ok=True)


def create_temp_path(files_dir: Path) -> Path:
    """Create a unique destination path for a Telegram cloud download."""
    files_dir.mkdir(parents=True, exist_ok=True)
    return files_dir / f".uploadbot-{uuid.uuid4().hex}.part"
