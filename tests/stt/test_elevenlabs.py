import json
import math
from pathlib import Path

import httpx
import pytest

from autocript.stt.elevenlabs import ElevenLabsScribe
from autocript.types import NonSpeech, SourceError

FIX = Path(__file__).parent.parent / "fixtures" / "stt" / "elevenlabs_ornek.json"


def test_parse():
    t = ElevenLabsScribe.parse(json.loads(FIX.read_text(encoding="utf-8")))
    assert [w.text for w in t.words] == ["Merhaba", "dünya"]
    assert t.words[0].confidence == pytest.approx(math.exp(-0.05))
    assert 0 <= t.words[1].confidence <= 1
    assert t.non_speech == [NonSpeech(1.0, 4.0, "music")]
    assert t.timing == "word"
    assert t.language == "tr"
    assert t.provider == "elevenlabs"
    assert t.cost_usd is None


def test_bos_yanit():
    t = ElevenLabsScribe.parse({"language_code": "tur", "text": "", "words": []})
    assert t.words == []


def _adapter(captured, status=200):
    def handler(request: httpx.Request):
        captured.append(request)
        return httpx.Response(status, json={"language_code": "en", "words": []})

    return ElevenLabsScribe("KEY", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_istek_bicimi(tmp_path):
    ses = tmp_path / "a.wav"
    ses.write_bytes(b"RIFF")
    cap = []
    _adapter(cap).transcribe_raw(ses, None)
    req = cap[0]
    assert req.method == "POST" and req.url.path == "/v1/speech-to-text"
    assert req.headers["xi-api-key"] == "KEY"
    body = req.content.decode("latin-1")
    assert 'name="model_id"' in body and "scribe_v3" in body
    assert 'name="timestamps_granularity"' in body and "word" in body
    assert 'name="tag_audio_events"' in body and "true" in body
    assert 'name="language_code"' not in body
    cap.clear()
    _adapter(cap).transcribe_raw(ses, "tr")
    assert 'name="language_code"' in cap[0].content.decode("latin-1")


def test_http_hatasi(tmp_path):
    ses = tmp_path / "a.wav"
    ses.write_bytes(b"x")
    with pytest.raises(SourceError) as e:
        _adapter([], status=500).transcribe_raw(ses, None)
    assert e.value.code == "STT_HATA"
