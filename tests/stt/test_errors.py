import httpx
import pytest

from autocript.stt._errors import redact
from autocript.stt.elevenlabs import ElevenLabsScribe
from autocript.stt.groq import GroqWhisper
from autocript.types import SourceError

KEY = "abcd1234"
ADAPTORLER = [ElevenLabsScribe, GroqWhisper]


def _kur(cls, handler):
    return cls(KEY, client=httpx.Client(transport=httpx.MockTransport(handler)))


def _ses(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"x")
    return p


def test_redact():
    assert redact("key=abcd1234 x", ["abcd1234", None, ""]) == "key=*** x"
    assert redact("abc x", ["abc"]) == "abc x"


@pytest.mark.parametrize("cls", ADAPTORLER)
def test_http_hatasi_govde_ve_maske(cls, tmp_path):
    def handler(request):
        return httpx.Response(400, json={"detail": "invalid key abcd1234"})

    with pytest.raises(SourceError) as ei:
        _kur(cls, handler).transcribe_raw(_ses(tmp_path), "tr")
    e = ei.value
    assert e.code == "STT_HATA"
    assert "400" in e.detail  # ekrandaki metin katalogdan; ayrıntı günlüğe
    assert "invalid key" in e.detail
    assert "abcd1234" not in str(e)
    assert "***" in e.detail


@pytest.mark.parametrize("cls", ADAPTORLER)
def test_ag_hatasi(cls, tmp_path):
    def handler(request):
        raise httpx.ConnectError("bağlantı yok")

    with pytest.raises(SourceError) as ei:
        _kur(cls, handler).transcribe_raw(_ses(tmp_path), "tr")
    assert "ConnectError" in ei.value.detail
    assert "bağlantı yok" in ei.value.detail


@pytest.mark.parametrize("cls", ADAPTORLER)
def test_govde_kesilir(cls, tmp_path):
    def handler(request):
        return httpx.Response(500, text="x" * 2000)

    with pytest.raises(SourceError) as ei:
        _kur(cls, handler).transcribe_raw(_ses(tmp_path), "tr")
    assert len(ei.value.detail) <= 600


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("cls", ADAPTORLER)
def test_anahtar_reddedildi(cls, status, tmp_path):
    def handler(request):
        return httpx.Response(status, json={"detail": "bad key abcd1234"})

    with pytest.raises(SourceError) as ei:
        _kur(cls, handler).transcribe_raw(_ses(tmp_path), "tr")
    e = ei.value
    assert e.code == "ANAHTAR_REDDEDILDI"
    assert e.upload_fallback is False
    assert "anahtarı reddedildi" in e.message
    assert "Anahtarlar sayfasından" in e.message
    assert set(e.params) == {"provider"}
    assert f"HTTP {status}" in e.detail
    assert "abcd1234" not in str(e)


@pytest.mark.parametrize("cls", ADAPTORLER)
def test_http_500_stt_hata(cls, tmp_path):
    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(SourceError) as ei:
        _kur(cls, handler).transcribe_raw(_ses(tmp_path), "tr")
    assert ei.value.code == "STT_HATA"
    assert ei.value.upload_fallback is True
