"""Konsol metinlerinin İngilizce çıktısı (conftest varsayılanı tr; burada ezilir)."""

import hashlib
import io
import socket
import zipfile

import httpx
import pytest

from autocript.yerel import araclar, baslat
from autocript.yerel.araclar import AracHatasi, ensure_ffmpeg


@pytest.fixture(autouse=True)
def _ingilizce(monkeypatch):
    monkeypatch.setenv("AUTOCRIPT_KONSOL_DIL", "en")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{araclar.FFMPEG_ZIP_KOK}bin/ffmpeg.exe", b"x")
    return buf.getvalue()


def test_ffmpeg_sha_hatasi_ingilizce(tmp_path, monkeypatch):
    monkeypatch.setattr(araclar, "FFMPEG_SHA256", "0" * 64)
    said = []
    with pytest.raises(AracHatasi) as ei:
        ensure_ffmpeg(
            tmp_path, client=_client(lambda r: httpx.Response(200, content=_zip())), say=said.append
        )
    assert said == ["ffmpeg is downloading (first launch only, about 77 MB)..."]
    msg = str(ei.value)
    assert msg.startswith("Could not download ffmpeg.")
    assert "(details: SHA-256 mismatch)" in msg
    assert "ayrıntı" not in msg


def test_ffmpeg_bozuk_arsiv_ingilizce(tmp_path, monkeypatch):
    data = b"not a zip"
    monkeypatch.setattr(araclar, "FFMPEG_SHA256", hashlib.sha256(data).hexdigest())
    with pytest.raises(AracHatasi) as ei:
        ensure_ffmpeg(
            tmp_path, client=_client(lambda r: httpx.Response(200, content=data)), say=lambda *_: None
        )
    assert "(details: corrupt archive)" in str(ei.value)


def test_instapuller_hata_uyarisi_ingilizce(tmp_path, monkeypatch):
    monkeypatch.setattr(araclar, "INSTAPULLER_SHA256", "0" * 64)
    said = []
    ok = araclar.ensure_instapuller(
        tmp_path,
        client=_client(lambda r: httpx.Response(200, content=b"zip")),
        run=lambda *a, **k: None,
        say=said.append,
    )
    assert ok is False
    assert said[0] == "The video download tool is being installed (first launch only)..."
    assert said[1].startswith("The video download tool could not be installed;")
    assert said[2] == "(details: AracHatasi: SHA-256 mismatch)"


def test_instapuller_hata_uyarisi_turkce(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCRIPT_KONSOL_DIL", "tr")
    monkeypatch.setattr(araclar, "INSTAPULLER_SHA256", "0" * 64)
    said = []
    araclar.ensure_instapuller(
        tmp_path,
        client=_client(lambda r: httpx.Response(200, content=b"zip")),
        run=lambda *a, **k: None,
        say=said.append,
    )
    assert said[2] == "(ayrıntı: AracHatasi: SHA-256 eşleşmedi)"


def test_pick_socket_hatasi_ingilizce(monkeypatch):
    class Dolu:
        def setsockopt(self, *a):
            pass

        def bind(self, *a):
            raise OSError("dolu")

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", lambda *a, **k: Dolu())
    with pytest.raises(AracHatasi) as ei:
        baslat.pick_socket(9000, 3)
    assert str(ei.value).startswith("No free port was found between 9000 and 9002.")


def test_zaten_acik_mesaji_ingilizce(tmp_path, monkeypatch, capsys):
    baslat.write_instance(tmp_path / "oturum.json", 8000, "t")
    monkeypatch.setattr(baslat, "instance_alive", lambda *a: True)
    monkeypatch.setattr(baslat, "load_settings", lambda: type("S", (), {"media_dir": tmp_path})())
    assert baslat._calistir(True) == 0
    assert "The app is already open. Opening it in the browser." in capsys.readouterr().out
