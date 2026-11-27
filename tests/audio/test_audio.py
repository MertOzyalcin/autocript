import json
import subprocess

import numpy as np
import pytest

from autocript.audio import decode_pcm, probe, to_flac
from autocript.config import load_settings
from autocript.types import SourceError


def _audio_stream(path):
    r = subprocess.run(
        [load_settings().ffprobe_bin, "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
    )
    return [s for s in json.loads(r.stdout)["streams"] if s["codec_type"] == "audio"][0]


@pytest.mark.parametrize(
    "video_codec",
    ["h264", "hevc", "vp9", None],
    ids=["mp4", "mov-hevc", "webm", "m4a"],
)
def test_bicim_cesitleri(make_media, tmp_path, video_codec):
    src = make_media("tone_silence_tone", 3, video_codec=video_codec)
    assert probe(src).has_audio is True
    flac = to_flac(src, tmp_path / "out.flac")
    assert abs(probe(flac).duration_s - 3.0) <= 0.1
    info = _audio_stream(flac)
    assert int(info["sample_rate"]) == 16000
    assert int(info["channels"]) == 1


def test_ses_izi_yok(make_media, tmp_path):
    src = make_media("tone", 2, video_codec="h264", audio=False)
    assert probe(src).has_audio is False
    with pytest.raises(SourceError) as e:
        to_flac(src, tmp_path / "o.flac")
    assert e.value.code == "DOSYA_SES_YOK"


def test_bozuk_dosya(tmp_path):
    bad = tmp_path / "bozuk.mp4"
    bad.write_bytes(np.random.default_rng(0).bytes(1024))
    with pytest.raises(SourceError) as e:
        probe(bad)
    assert e.value.code == "DOSYA_BOZUK"
    assert e.value.message == "Dosya okunamadı. Desteklenen bir video ya da ses dosyası yükleyin."
    assert "bozuk" not in e.value.message and "@" not in e.value.message and str(tmp_path) not in e.value.message
    assert e.value.detail


def test_run_oserror_mesaji_temiz(monkeypatch):
    from autocript.audio import ffmpeg

    def boom(*a, **k):
        raise OSError("C:/gizli/yol/ffmpeg.exe bulunamadi")

    monkeypatch.setattr(ffmpeg.subprocess, "run", boom)
    with pytest.raises(SourceError) as e:
        ffmpeg._run(["C:/gizli/yol/ffmpeg.exe"])
    assert e.value.message == "Dosya okunamadı. Desteklenen bir video ya da ses dosyası yükleyin."
    assert "gizli" not in e.value.message
    assert "gizli" in e.value.detail


def test_uzun_dosya_suresi(make_media):
    src = make_media("silence", 190)
    assert abs(probe(src).duration_s - 190) <= 0.1


def test_decode_pcm(make_media, tmp_path):
    src = make_media("tone", 2)
    flac = to_flac(src, tmp_path / "x.flac")
    pcm = decode_pcm(flac)
    assert pcm.shape == (32000,)
    assert pcm.dtype == np.float32
    assert np.abs(pcm).max() <= 1.0
