"""Ayarlar: .env dosyası ve ortam değişkenleri. Ortam değişkeni .env'deki değeri ezer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

# Yükleme biçim listesi (İL §6.8). Listede olmayan uzantı 415 DOSYA_BICIMI alır.
UPLOAD_EXTS: tuple[str, ...] = (
    ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp",
    ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma",
)


@dataclass
class Settings:
    elevenlabs_api_key: str | None = None
    groq_api_key: str | None = None
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    # Kilometre taşı 1
    stt_timeout_s: float = 60.0
    low_confidence_threshold: float = 0.80  # kullanıcı onayı, 2026-11-25
    nonspeech_detector: Literal["silero", "none"] = "none"  # K1, kullanıcı kararı 2026-11-25
    media_dir: Path = ROOT / "data" / "media"
    max_upload_mb: int = 500
    max_duration_s: float = 185.0
    job_concurrency: int = 3
    # Link (İL §6.2, KT2 Task 7: instapuller v0.3.0)
    instapuller_python: str = str(ROOT / "tools" / "instapuller" / "venv" / "Scripts" / "python.exe")
    instapuller_src: str = str(ROOT / "tools" / "instapuller" / "instapuller-0.3.0")
    # Site başına durum dosyası: <dizin>/instapuller-<site>.json (KT2 kararı 2).
    instapuller_state_dir: Path = ROOT / "data" / "state"
    # YouTube için JS çalışma ortamı; instapuller'a --js-runtime-bin ile verilir (Task 9 kurar).
    js_runtime_bin: str = str(ROOT / "tools" / "js" / "qjs.exe")
    max_link_mb: int = 200
    link_timeout_s: float = 180.0


_KEYS = (
    "elevenlabs_api_key",
    "groq_api_key",
)


def _tool_path(value: str) -> str:
    """Göreli araç yolunu (ör. tools/ffmpeg/bin/ffmpeg.exe) proje köküne göre çözer; yalın ad (ffmpeg) PATH için kalır."""
    p = Path(value)
    if p.is_absolute() or len(p.parts) == 1:
        return value
    return str(ROOT / p)


def _proje_yolu(value: str) -> str:
    """Dizin/dosya yolu göreliyse (tek parçalı ya da ./ ön ekli dahil) proje köküne göre çözer."""
    p = Path(value)
    return value if p.is_absolute() else str(ROOT / p)


def _default_tool(root: Path, exe: str) -> str:
    """Proje içi kopyayı (root/tools/ffmpeg/bin/<exe>) döndürür; yoksa PATH için yalın adı (ör. ffmpeg)."""
    p = root / "tools" / "ffmpeg" / "bin" / exe
    return str(p) if p.is_file() else Path(exe).stem


def load_settings(env_file: Path | None = ROOT / ".env") -> Settings:
    """Ayarları yükler. env_file=None verilirse yalnızca ortam okunur."""
    values: dict[str, str | None] = {}
    if env_file is not None and Path(env_file).is_file():
        values.update(dotenv_values(env_file))
    values.update(os.environ)

    def get(name: str) -> str | None:
        v = values.get(name.upper())
        return v.strip() if v and v.strip() else None

    s = Settings(**{k: get(k) for k in _KEYS})
    s.ffmpeg_bin = _tool_path(get("ffmpeg_bin") or _default_tool(ROOT, "ffmpeg.exe"))
    s.ffprobe_bin = _tool_path(get("ffprobe_bin") or _default_tool(ROOT, "ffprobe.exe"))

    if (v := get("stt_timeout_s")) is not None:
        s.stt_timeout_s = float(v)
    if (v := get("low_confidence_threshold")) is not None:
        s.low_confidence_threshold = float(v)
    if (v := get("nonspeech_detector")) is not None:
        if v not in ("silero", "none"):
            raise ValueError(f"NONSPEECH_DETECTOR 'silero' ya da 'none' olmalı: {v!r}")
        s.nonspeech_detector = v  # type: ignore[assignment]
    if (v := get("media_dir")) is not None:
        s.media_dir = Path(_proje_yolu(v))
    if (v := get("max_upload_mb")) is not None:
        s.max_upload_mb = int(v)
    if (v := get("max_duration_s")) is not None:
        s.max_duration_s = float(v)
    if (v := get("job_concurrency")) is not None:
        s.job_concurrency = int(v)
    s.instapuller_python = _tool_path(
        get("instapuller_python") or str(ROOT / "tools" / "instapuller" / "venv" / "Scripts" / "python.exe")
    )
    s.instapuller_src = _proje_yolu(get("instapuller_src") or str(ROOT / "tools" / "instapuller" / "instapuller-0.3.0"))
    s.instapuller_state_dir = Path(_proje_yolu(get("instapuller_state_dir") or str(ROOT / "data" / "state")))
    s.js_runtime_bin = _tool_path(get("js_runtime_bin") or str(ROOT / "tools" / "js" / "qjs.exe"))
    if (v := get("max_link_mb")) is not None:
        s.max_link_mb = int(v)
    # Eski .env satırı INSTAGRAM_TIMEOUT_S de kabul edilir; LINK_TIMEOUT_S önceliklidir.
    if (v := get("link_timeout_s") or get("instagram_timeout_s")) is not None:
        s.link_timeout_s = float(v)
    return s
