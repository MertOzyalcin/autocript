"""İş klasörleri, güvenli dosya yükleme ve eski klasör temizliği."""

from __future__ import annotations

import re
import secrets
import shutil
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from autocript.config import UPLOAD_EXTS
from autocript.sources.hatalar import hata

_JOB_ID_RE = re.compile(r"^j_[A-Za-z0-9]{12,32}$")
_EXT_RE = re.compile(r"^[a-z0-9]{1,5}$")


def new_job_id() -> str:
    return "j_" + secrets.token_hex(8)


def _check_id(job_id: str) -> None:
    if not _JOB_ID_RE.fullmatch(job_id):
        raise ValueError(f"Geçersiz iş kimliği: {job_id!r}")


def job_dir(media_dir: Path, job_id: str) -> Path:
    _check_id(job_id)
    path = media_dir / "jobs" / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(filename: str | None) -> str:
    ext = ""
    if filename:
        base = filename.replace("\\", "/").rsplit("/", 1)[-1]
        if "." in base:
            ext = base.rsplit(".", 1)[-1].lower()
    if ext and _EXT_RE.fullmatch(ext):
        return f"upload.{ext}"
    return "upload"


async def save_upload(
    chunks: AsyncIterator[bytes],
    dest_dir: Path,
    filename: str | None,
    max_bytes: int,
) -> Path:
    # Biçim listesi dışı uzantı: ilk bayt yazılmadan reddedilir (İL §6.8).
    ad = _safe_name(filename)
    if not ad.startswith("upload.") or "." + ad.split(".", 1)[1] not in UPLOAD_EXTS:
        raise hata("DOSYA_BICIMI")
    path = dest_dir / ad
    total = 0
    try:
        with open(path, "wb") as f:
            async for chunk in chunks:
                total += len(chunk)
                if total > max_bytes:
                    raise hata("DOSYA_BUYUK", varyant="yukleme")
                f.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def remove_job_dir(media_dir: Path, job_id: str) -> None:
    _check_id(job_id)
    shutil.rmtree(media_dir / "jobs" / job_id, ignore_errors=True)


def sweep(
    media_dir: Path,
    is_active: Callable[[str], bool],
    now: float,
    max_age_s: float = 1800,
) -> list[str]:
    jobs = media_dir / "jobs"
    if not jobs.is_dir():
        return []
    removed: list[str] = []
    for d in jobs.iterdir():
        if not d.is_dir() or not _JOB_ID_RE.fullmatch(d.name):
            continue
        if now - d.stat().st_mtime <= max_age_s or is_active(d.name):
            continue
        shutil.rmtree(d, ignore_errors=True)
        removed.append(d.name)
    return removed
