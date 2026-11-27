import os
import subprocess
import sys
from pathlib import Path

import pytest

from autocript.config import Settings
from autocript.jobs.pipeline import make_detector
from autocript.nonspeech.null import NullDetector

REPO = Path(__file__).resolve().parents[2]


def test_olc_sabit_bag_bir_kez(tmp_path):
    from dagitim.boyut import olc

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    asil = tmp_path / "a" / "dosya.bin"
    asil.write_bytes(b"x" * 1000)
    try:
        os.link(asil, tmp_path / "b" / "ikinci.bin")
    except OSError:
        pytest.skip("sabit bağ desteklenmiyor")
    (tmp_path / "b" / "ayri.bin").write_bytes(b"y" * 10)
    r = olc(tmp_path)
    assert r["TOPLAM"] == (1010, 2)
    # bağ ilk görülen klasörde sayılır; ikinci klasörde ikinci kez sayılmaz
    assert r["a"][1] + r["b"][1] == 2
    assert r["a"][0] + r["b"][0] == 1010


def test_olc_ust_klasor_ve_toplam(tmp_path):
    from dagitim.boyut import olc

    (tmp_path / "x" / "y").mkdir(parents=True)
    (tmp_path / "x" / "y" / "d.bin").write_bytes(b"1" * 5)
    (tmp_path / "z.bin").write_bytes(b"2" * 7)
    r = olc(tmp_path)
    assert r["x"] == (5, 1)
    assert r["TOPLAM"] == (12, 2)


def test_vad_yokken_pipeline_yuklenir():
    kod = (
        "import sys\n"
        "sys.modules['numpy'] = None\n"
        "sys.modules['onnxruntime'] = None\n"
        "import autocript.web.app\n"
        "from autocript.config import Settings\n"
        "from autocript.jobs.pipeline import make_detector\n"
        "from autocript.nonspeech.null import NullDetector\n"
        "assert isinstance(make_detector(Settings(nonspeech_detector='none')), NullDetector)\n"
        "try:\n"
        "    make_detector(Settings(nonspeech_detector='silero'))\n"
        "except RuntimeError as e:\n"
        "    assert str(e) == \"Konuşmasız bölüm dedektörü kurulu değil. baslat.cmd'yi kapatıp yeniden açın.\", str(e)\n"
        "else:\n"
        "    raise SystemExit('RuntimeError beklenirdi')\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", kod], cwd=REPO, capture_output=True, text=True, encoding="utf-8"
    )
    assert r.returncode == 0, r.stderr


def test_make_detector_none_null():
    assert isinstance(make_detector(Settings(nonspeech_detector="none")), NullDetector)


def test_baslat_vad_grubu():
    data = (REPO / "baslat.cmd").read_bytes()
    data.decode("ascii")
    assert data.count(b"\n") == data.count(b"\r\n")
    metin = data.decode("ascii")
    assert "findstr" in metin
    assert "NONSPEECH_DETECTOR=silero" in metin
    assert "--group vad" in metin


@pytest.mark.parametrize("ad", ["baslat.cmd", "dagitim/uv-indir.ps1"])
def test_baslatici_betikleri_saf_ascii(ad):
    # Konsol kod sayfasına bağımlı olmamak için Türkçe harf yok; Türkçe metin aksansız yazılır.
    (REPO / ad).read_bytes().decode("ascii")


def test_baslatici_konsol_dili_degiskeni():
    cmd = (REPO / "baslat.cmd").read_text(encoding="ascii")
    assert "AUTOCRIPT_KONSOL_DIL" in cmd
    assert "CurrentUICulture" in cmd
    assert "AUTOCRIPT_KONSOL_DIL" in (REPO / "dagitim" / "uv-indir.ps1").read_text(encoding="ascii")
