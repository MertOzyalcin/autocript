"""ffmpeg/ffprobe sarmalayıcıları.

İkili yollar configure_tools() ile ayarlanır (create_app bunu Settings'ten çağırır).
Çağrılmadıysa yollar ilk kullanımda bir kez load_settings()'ten okunur ve önbelleğe alınır.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from autocript.config import load_settings
from autocript.sources.hatalar import hata
from autocript.types import ProbeResult, SourceError

if TYPE_CHECKING:
    import numpy as np


_TOOLS: tuple[str, str] | None = None  # (ffmpeg, ffprobe)


def configure_tools(ffmpeg_bin: str, ffprobe_bin: str) -> None:
    """Modül düzeyinde araç yollarını ayarlar."""
    global _TOOLS
    _TOOLS = (ffmpeg_bin, ffprobe_bin)


def _tools() -> tuple[str, str]:
    global _TOOLS
    if _TOOLS is None:
        s = load_settings()
        _TOOLS = (s.ffmpeg_bin, s.ffprobe_bin)
    return _TOOLS


def _bozuk(path: Path, stderr: bytes | str = b"") -> SourceError:
    detail = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
    return hata(
        "DOSYA_BOZUK",
        detail=detail.strip()[-300:] or f"{Path(path).name} okunamadı",
        varyant="yukleme",
    )


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True)
    except OSError as e:
        err = hata("DOSYA_BOZUK", detail=f"{cmd[0]} çalıştırılamadı: {e}", varyant="yukleme")
        err.upload_fallback = False
        raise err from e


def probe(path: Path) -> ProbeResult:
    """Süre ve ses izi; okunamayan dosyada SourceError("DOSYA_BOZUK")."""
    path = Path(path)
    r = _run(
        [_tools()[1], "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    )
    if r.returncode != 0:
        raise _bozuk(path, r.stderr)
    try:
        data = json.loads(r.stdout)
        fmt = data["format"]
        streams = data.get("streams", [])
        if not streams:
            raise ValueError("akış yok")
        duration = float(fmt["duration"])
        container = str(fmt["format_name"])
    except (ValueError, KeyError, TypeError) as e:
        raise _bozuk(path, str(e)) from e
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return ProbeResult(duration_s=duration, has_audio=has_audio, container=container)


def to_flac(path: Path, out: Path, *, check_audio: bool = True) -> Path:
    """16 kHz mono FLAC; ses izi yoksa SourceError("DOSYA_SES_YOK").

    check_audio=False: çağıran dosyayı zaten probe ettiyse ikinci ffprobe atlanır.
    """
    path, out = Path(path), Path(out)
    if check_audio and not probe(path).has_audio:
        raise hata("DOSYA_SES_YOK", varyant="yukleme")
    r = _run(
        [_tools()[0], "-y", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "flac", str(out)]
    )
    if r.returncode != 0:
        raise _bozuk(path, r.stderr)
    return out


def decode_pcm(path: Path) -> np.ndarray:
    """float32, 16 kHz mono, [-1, 1]."""
    import numpy as np  # yalnızca VAD yolunda gerekir; ürün çekirdeği numpy'sız açılır

    path = Path(path)
    r = _run(
        [_tools()[0], "-v", "error", "-i", str(path), "-vn", "-f", "s16le", "-ac", "1",
         "-ar", "16000", "-"]
    )
    if r.returncode != 0:
        raise _bozuk(path, r.stderr)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
