import subprocess

import numpy as np
import pytest

from autocript.audio import decode_pcm
from autocript.config import load_settings
from autocript.nonspeech.null import NullDetector
from autocript.nonspeech.silero import SileroDetector, classify_gap, gaps_from_speech


def test_null_detector(tmp_path):
    d = NullDetector()
    assert d.name == "null"
    assert d.detect(tmp_path / "yok.flac") == []


def test_gaps_from_speech():
    assert gaps_from_speech([(0.5, 1.0), (1.5, 3.0)], 5.0) == [(3.0, 5.0)]


def test_classify_gap():
    assert classify_gap(np.zeros(16000, dtype=np.float32)) == "silence"
    rng = np.random.default_rng(0)
    noise = (rng.uniform(-1, 1, 16000) * 0.1 * np.sqrt(3)).astype(np.float32)  # RMS -20 dBFS
    assert classify_gap(noise) == "unknown"


def _flac(make_media, kind, seconds, tmp_path):
    src = make_media(kind, seconds)
    out = tmp_path / f"{kind}.flac"
    subprocess.run(
        [load_settings().ffmpeg_bin, "-y", "-v", "error", "-i", str(src), "-ar", "16000", "-ac", "1", str(out)],
        check=True,
    )
    return out


@pytest.mark.model
def test_silero_sessizlik(make_media, tmp_path):
    flac = _flac(make_media, "silence", 4, tmp_path)
    gaps = SileroDetector().detect(flac)
    assert len(gaps) == 1
    assert gaps[0].start == pytest.approx(0, abs=0.1)
    assert gaps[0].end == pytest.approx(4.0, abs=0.1)
    assert gaps[0].kind == "silence"


@pytest.mark.model
def test_silero_gurultu(make_media, tmp_path):
    # make_media("noise") genlik 0.1 (-20 dBFS tepe), yani RMS -45 dBFS'in çok üstünde
    flac = _flac(make_media, "noise", 4, tmp_path)
    gaps = SileroDetector().detect(flac)
    assert sum(g.end - g.start for g in gaps) >= 3.9
    assert all(g.kind == "unknown" for g in gaps)


def test_silero_sha_uyusmazligi(tmp_path, monkeypatch):
    import autocript.nonspeech.silero as s

    monkeypatch.setattr(s, "_fetch", lambda url, dest: dest.write_bytes(b"sahte"))
    with pytest.raises(RuntimeError, match="SHA-256"):
        SileroDetector(model_dir=tmp_path).detect(tmp_path / "x.flac")
    assert not (tmp_path / "silero_vad.onnx").exists()


def test_silero_uyusmayan_model_silinir(tmp_path, monkeypatch):
    import autocript.nonspeech.silero as s

    (tmp_path / "silero_vad.onnx").write_bytes(b"bozuk")

    def boom(url, dest):
        raise OSError("ağ yok")

    monkeypatch.setattr(s, "_fetch", boom)
    with pytest.raises((RuntimeError, OSError)):
        SileroDetector(model_dir=tmp_path).detect(tmp_path / "x.flac")
    assert not (tmp_path / "silero_vad.onnx").exists()
