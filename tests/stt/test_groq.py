import json
from pathlib import Path

import httpx
import pytest

from autocript.stt.groq import GroqWhisper
from autocript.types import NonSpeech, SourceError

FIX = Path(__file__).parent.parent / "fixtures" / "stt" / "groq_ornek.json"


def test_parse():
    t = GroqWhisper.parse(json.loads(FIX.read_text(encoding="utf-8")))
    assert [w.text for w in t.words] == ["Merhaba", "dünya"]
    assert t.words[0].confidence is None
    assert t.non_speech == [NonSpeech(2.0, 5.0, "unknown")]
    assert t.language == "tr"
    assert t.timing == "word"
    assert t.provider == "groq"


def test_bos_yanit():
    t = GroqWhisper.parse({"language": "turkish", "text": ""})
    assert t.words == []


def test_istek_bicimi(tmp_path):
    ses = tmp_path / "a.wav"
    ses.write_bytes(b"x")
    cap = []

    def handler(request):
        cap.append(request)
        return httpx.Response(200, json={"language": "turkish", "words": []})

    g = GroqWhisper("KEY", client=httpx.Client(transport=httpx.MockTransport(handler)))
    g.transcribe_raw(ses, "tr")
    r = cap[0]
    assert r.url.path == "/openai/v1/audio/transcriptions"
    assert r.headers["authorization"] == "Bearer KEY"
    body = r.content.decode("latin-1")
    for s in ("whisper-large-v3", "verbose_json", "timestamp_granularities[]", "word", 'name="language"'):
        assert s in body


def test_http_hatasi(tmp_path):
    ses = tmp_path / "a.wav"
    ses.write_bytes(b"x")
    g = GroqWhisper("K", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, text="no"))))
    with pytest.raises(SourceError) as e:
        g.transcribe_raw(ses, None)
    assert e.value.code == "STT_HATA"
