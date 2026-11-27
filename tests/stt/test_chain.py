import httpx
import pytest

from autocript.config import Settings
from autocript.stt import SttOutcome
from autocript.stt.chain import SttChain, build_stt_chain
from autocript.stt.elevenlabs import ElevenLabsScribe
from autocript.stt.groq import GroqWhisper
from autocript.types import RawTranscript, SourceError


def _raw(provider: str) -> RawTranscript:
    return RawTranscript("tr", "word", [], [], [], provider, "m", None)


class Fake:
    def __init__(self, name, result=None, error=None):
        self.name = name
        self.result = result
        self.error = error
        self.calls = 0

    def transcribe(self, audio, language):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def _boom(request):
    raise httpx.ReadTimeout("zaman asimi", request=request)


def _timeout_client():
    return httpx.Client(transport=httpx.MockTransport(_boom))


def test_birincil_basarili(tmp_path):
    p = Fake("elevenlabs", _raw("elevenlabs"))
    f = Fake("groq", _raw("groq"))
    out = SttChain(p, f).transcribe(tmp_path / "a.wav", "tr")
    assert isinstance(out, SttOutcome)
    assert out.used_fallback is False
    assert out.primary_error is None
    assert out.raw.provider == "elevenlabs"
    assert f.calls == 0


def test_birincil_hata_yedege_gecer(tmp_path):
    p = Fake("elevenlabs", error=SourceError("STT_HATA", "x", detail="HTTP 503"))
    f = Fake("groq", _raw("groq"))
    out = SttChain(p, f).transcribe(tmp_path / "a.wav", None)
    assert out.raw.provider == "groq"
    assert out.used_fallback is True
    assert out.primary_error.code == "STT_HATA"


def test_ikisi_de_hata(tmp_path):
    p = Fake("elevenlabs", error=SourceError("STT_HATA", "x", detail="HTTP 503"))
    f = Fake("groq", error=SourceError("STT_HATA", "y", detail="HTTP 429"))
    with pytest.raises(SourceError) as ei:
        SttChain(p, f).transcribe(tmp_path / "a.wav", None)
    e = ei.value
    assert e.code == "STT_HATA"
    assert "HTTP 503" in e.detail and "HTTP 429" in e.detail
    assert "elevenlabs" in e.detail and "groq" in e.detail


def test_yedek_yoksa_birincil_hata_yukari(tmp_path):
    p = Fake("groq", error=SourceError("STT_HATA", "x", detail="HTTP 503"))
    with pytest.raises(SourceError) as ei:
        SttChain(p, None).transcribe(tmp_path / "a.wav", None)
    assert "HTTP 503" in ei.value.detail


def test_baska_istisna_yedege_gecmez(tmp_path):
    p = Fake("elevenlabs", error=ValueError("bug"))
    f = Fake("groq", _raw("groq"))
    with pytest.raises(ValueError):
        SttChain(p, f).transcribe(tmp_path / "a.wav", None)
    assert f.calls == 0


def test_zaman_asimi_yedege_gecer(tmp_path):
    secret = "xi-gizli-anahtar-123"
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    p = ElevenLabsScribe(secret, client=_timeout_client())
    f = Fake("groq", _raw("groq"))
    out = SttChain(p, f).transcribe(audio, "tr")
    assert out.used_fallback is True
    assert out.raw.provider == "groq"
    assert out.primary_error.code == "STT_HATA"
    assert secret not in (out.primary_error.detail or "")
    assert secret not in out.primary_error.message


def test_ikisi_de_hata_anahtar_sizmaz(tmp_path):
    a, b = "xi-gizli-anahtar-123", "gsk-gizli-anahtar-456"
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    chain = SttChain(
        ElevenLabsScribe(a, client=_timeout_client()),
        GroqWhisper(b, client=_timeout_client()),
    )
    with pytest.raises(SourceError) as ei:
        chain.transcribe(audio, None)
    blob = f"{ei.value.message} {ei.value.detail}"
    assert a not in blob and b not in blob


def test_build_zincir_anahtar_durumlari():
    c = build_stt_chain(Settings(elevenlabs_api_key="e-key-1", groq_api_key="g-key-1"))
    assert isinstance(c.primary, ElevenLabsScribe)
    assert isinstance(c.fallback, GroqWhisper)
    assert c.primary.client.timeout.read == 60.0

    c = build_stt_chain(Settings(groq_api_key="g-key-1", stt_timeout_s=30.0))
    assert isinstance(c.primary, GroqWhisper)
    assert c.fallback is None
    assert c.primary.client.timeout.read == 30.0

    with pytest.raises(RuntimeError, match="STT anahtarı yok"):
        build_stt_chain(Settings())


def _red(detail="HTTP 401: x"):
    return SourceError("ANAHTAR_REDDEDILDI", "m", detail=detail, upload_fallback=False)


def _hata(detail="HTTP 500: y"):
    return SourceError("STT_HATA", "m", detail=detail)


def test_birincil_reddedildi_yedek_basarili(tmp_path):
    p = Fake("elevenlabs", error=_red())
    f = Fake("groq", _raw("groq"))
    out = SttChain(p, f).transcribe(tmp_path / "a.wav", None)
    assert out.used_fallback is True
    assert out.raw.provider == "groq"
    assert out.primary_error.code == "ANAHTAR_REDDEDILDI"


def test_birincil_reddedildi_yedek_hata(tmp_path):
    p = Fake("elevenlabs", error=_red())
    f = Fake("groq", error=_hata())
    with pytest.raises(SourceError) as ei:
        SttChain(p, f).transcribe(tmp_path / "a.wav", None)
    e = ei.value
    assert e.code == "ANAHTAR_REDDEDILDI"
    assert e.upload_fallback is False
    assert "anahtarı" in e.message or e.message == "m"
    assert "elevenlabs" in e.detail and "groq" in e.detail
    assert "HTTP 401" in e.detail and "HTTP 500" in e.detail


def test_birincil_hata_yedek_reddedildi(tmp_path):
    p = Fake("elevenlabs", error=_hata())
    f = Fake("groq", error=_red("HTTP 403: z"))
    with pytest.raises(SourceError) as ei:
        SttChain(p, f).transcribe(tmp_path / "a.wav", None)
    e = ei.value
    assert e.code == "ANAHTAR_REDDEDILDI"
    assert e.upload_fallback is False
    assert "HTTP 500" in e.detail and "HTTP 403" in e.detail


def test_ikisi_de_500_stt_hata(tmp_path):
    p = Fake("elevenlabs", error=_hata())
    f = Fake("groq", error=_hata())
    with pytest.raises(SourceError) as ei:
        SttChain(p, f).transcribe(tmp_path / "a.wav", None)
    assert ei.value.code == "STT_HATA"
    assert ei.value.message == "Transkript motorları yanıt vermedi."


def test_yedek_yok_reddedildi_oldugu_gibi(tmp_path):
    p = Fake("elevenlabs", error=_red())
    with pytest.raises(SourceError) as ei:
        SttChain(p, None).transcribe(tmp_path / "a.wav", None)
    assert ei.value.code == "ANAHTAR_REDDEDILDI"
    assert ei.value.upload_fallback is False
