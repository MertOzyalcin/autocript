"""Ortak test yardımcıları: sentetik medya üretici (ffmpeg lavfi), gerçek instapuller koruması."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from autocript.config import load_settings

# video_codec -> (aday kodlayıcılar [(ad, argümanlar)], uzantı, ses kodlayıcı).
# Kurulu ffmpeg'de ilk bulunan aday kullanılır. KT2 Task 9'dan beri proje içi ffmpeg LGPL
# shared sürümdür: libx264/libx265 yoktur, yerlerine libopenh264/libkvazaar kullanılır.
_VIDEO = {
    "h264": (
        [("libx264", ["-c:v", "libx264", "-pix_fmt", "yuv420p"]),
         ("libopenh264", ["-c:v", "libopenh264", "-pix_fmt", "yuv420p"])],
        "mp4", "aac",
    ),
    "hevc": (
        [("libx265", ["-c:v", "libx265", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]),
         ("libkvazaar", ["-c:v", "libkvazaar", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"])],
        "mov", "aac",
    ),
    "vp9": (
        [("libvpx-vp9", ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40", "-pix_fmt", "yuv420p"])],
        "webm", "libopus",
    ),
}

_SR = 44100


def _audio_source(kind: str, seconds: float) -> str:
    if kind == "tone_silence_tone":
        # 1 sn 440 Hz, 1 sn sessizlik, kalanı ton (3 sn için 1/1/1)
        return f"aevalsrc=sin(2*PI*440*t)*(lt(t\\,1)+gte(t\\,2)):d={seconds}:s={_SR}"
    if kind == "tone":
        return f"sine=frequency=440:sample_rate={_SR}:duration={seconds}"
    if kind == "silence":
        return f"anullsrc=r={_SR}:cl=mono:d={seconds}"
    if kind == "noise":
        return f"anoisesrc=d={seconds}:r={_SR}:a=0.1"
    raise ValueError(f"bilinmeyen kind: {kind!r}")


@pytest.fixture
def make_media(tmp_path):
    """Fabrika döner: make_media(kind, seconds, *, video_codec=None, audio=True) -> Path.

    kind (ses içeriği; yeni değerler _audio_source'a eklenir, imza değişmez):
      "tone_silence_tone"  1 sn 440 Hz ton, 1 sn sessizlik, kalanı ton (aevalsrc)
      "tone"               sürekli 440 Hz ton (sine)
      "silence"            saf sessizlik (anullsrc)
      "noise"              beyaz gürültü, genlik 0.1 (anoisesrc)
    video_codec: None -> yalnızca ses, .m4a (AAC); "h264" -> .mp4 (AAC);
      "hevc" -> .mov (AAC); "vp9" -> .webm (Opus). Video testsrc ile üretilir.
      Kodlayıcı kurulu ffmpeg'de yoksa pytest.skip.
    audio: False ise ses izi olmaz; video_codec None ise h264 kullanılır.
    Dosyalar pytest tmp_path altına yazılır.
    """
    counter = {"n": 0}

    def factory(kind: str, seconds: float, *, video_codec: str | None = None, audio: bool = True) -> Path:
        if video_codec is None and not audio:
            video_codec = "h264"
        if video_codec is not None and video_codec not in _VIDEO:
            raise ValueError(f"bilinmeyen video_codec: {video_codec!r}")
        ffmpeg = load_settings().ffmpeg_bin
        counter["n"] += 1
        cmd = [ffmpeg, "-y", "-v", "error"]
        if video_codec is None:
            ext, vargs, acodec = "m4a", [], "aac"
        else:
            adaylar, ext, acodec = _VIDEO[video_codec]
            enc = subprocess.run([ffmpeg, "-v", "error", "-encoders"], capture_output=True, text=True).stdout
            kurulu = {satir.split()[1] for satir in enc.splitlines() if len(satir.split()) > 1}
            vargs = next((a for ad, a in adaylar if ad in kurulu), None)
            if vargs is None:
                pytest.skip(f"ffmpeg derlemesinde {video_codec} kodlayıcısı yok")
            cmd += ["-f", "lavfi", "-i", f"testsrc=size=320x240:rate=25:duration={seconds}"]
        out = tmp_path / f"{kind}_{counter['n']}.{ext}"
        if audio:
            cmd += ["-f", "lavfi", "-i", _audio_source(kind, seconds)]
        cmd += vargs
        cmd += ["-c:a", acodec] if audio else ["-an"]
        cmd += ["-t", str(seconds), str(out)]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg başarısız: {r.stderr.decode(errors='replace')}")
        return out

    return factory


@pytest.fixture(autouse=True)
def _gercek_instapuller_yasak(tmp_path, monkeypatch):
    """Hiçbir test geliştiricinin .env'indeki gerçek instapuller'ı çalıştıramaz (İL §7).

    Sahte modülü kullanan testler bu değerleri açıkça ezer.
    """
    monkeypatch.setenv("INSTAPULLER_PYTHON", str(tmp_path / "yok" / "python.exe"))
    monkeypatch.setenv("INSTAPULLER_SRC", str(tmp_path / "yok" / "src"))
    monkeypatch.setenv("INSTAPULLER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("JS_RUNTIME_BIN", str(tmp_path / "yok" / "qjs.exe"))


@pytest.fixture(autouse=True)
def _konsol_dili_tr(monkeypatch):
    """Konsol metinleri varsayılan olarak Türkçe test edilir; İngilizce testler değişkeni ezer."""
    monkeypatch.setenv("AUTOCRIPT_KONSOL_DIL", "tr")


@pytest.fixture
def ffprobe_yolu() -> str:
    """Proje içindeki ffprobe kopyası (Settings dataclass varsayılanı "ffprobe" PATH'e bakar)."""
    return load_settings().ffprobe_bin
