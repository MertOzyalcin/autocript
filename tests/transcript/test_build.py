import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from autocript.transcript import build
from autocript.types import NonSpeech, RawSegment, RawTranscript, RawWord, SourceMeta

SCHEMA = json.loads((Path(__file__).parents[2] / "schema" / "transcript-v1.json").read_text("utf-8"))
V = Draft202012Validator(SCHEMA)


def meta(d=20.0):
    return SourceMeta("upload", None, None, None, None, None, d)


def raw(words, language="tr", non_speech=(), provider="elevenlabs", model="scribe_v3"):
    return RawTranscript(language, "word", list(words), [], list(non_speech), provider, model, None)


def w(t, s, e, c=0.9):
    return RawWord(t, s, e, c)


def b(r, m=None, vad=(), thr=0.8, **kw):
    doc = build(r, m or meta(), "j1", list(vad), low_conf_threshold=thr, **kw)
    V.validate(doc)
    return doc


def test_build_ornek_gecerli():
    r = raw([w("Merhaba", 0.42, 0.81), w("güzel", 0.9, 1.1), w("dünya.", 1.2, 1.5)])
    d = b(r, now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    assert d["engine"] == {"route": "stt", "provider": r.provider, "model": r.model}
    assert d["schema_version"] == "1.0" and d["created_at"] == "2026-01-02T03:04:05Z"
    assert d["segments"][0]["word_range"] == [0, 3]


def test_cumle_bolme_noktalama():
    d = b(raw([w("Merhaba.", 0, 0.5), w("dünya", 0.6, 1.0)]))
    assert len(d["segments"]) == 2


def test_cumle_bolme_bosluk():
    assert len(b(raw([w("a", 0, 0.5), w("b", 1.3, 1.5)]))["segments"]) == 2
    assert len(b(raw([w("a", 0, 0.5), w("b", 1.1, 1.5)]))["segments"]) == 1


def test_cumle_bolme_uzunluk():
    d = b(raw([w("kelimeler", i * 0.3, i * 0.3 + 0.25) for i in range(20)]))
    assert len(d["segments"]) > 1
    assert all(len(s["text"]) <= 84 for s in d["segments"])


def test_cumle_konusmasiz_aralikta_bolunur():
    d = b(raw([w("a", 0, 0.5), w("b", 0.6, 1.0), w("c", 1.9, 2.3)]), vad=[NonSpeech(1.2, 1.8, "silence")])
    assert [s["word_range"] for s in d["segments"]] == [[0, 2], [2, 3]]


def test_dakika_gruplama():
    r = raw([w("a", 10, 10.5), w("b.", 59.9, 60.0), w("c", 60.0, 60.5), w("d", 125, 126)])
    d = b(r, meta(130.0))
    assert len(d["minutes"]) == 3
    assert [m["segment_range"] for m in d["minutes"]] == [[0, 2], [2, 3], [3, 4]]
    assert d["minutes"][2]["end"] == 130.0


def test_dusuk_guven():
    r = raw([w("a", 0, 0.5, 0.5), w("b", 0.6, 1.0, 0.95), w("c", 1.1, 1.5, None)])
    assert [x["low_confidence"] for x in b(r)["words"]] == [True, False, False]


def test_yedek_motor_guven_null():
    r = raw([w("a", 0, 0.5, None), w("b", 0.6, 1.0, None)], provider="groq", model="whisper-large-v3")
    d = b(r)
    assert not any(x["low_confidence"] for x in d["words"])
    assert all(x["confidence"] is None for x in d["words"])


def test_konusma_yok():
    d = b(raw([]))
    assert d["words"] == [] and d["segments"] == []
    assert {"code": "KONUSMA_YOK", "message": "Videoda konuşma bulunamadı."} in d["warnings"]


def test_segment_zamanlama():
    r = RawTranscript(
        "tr", "segment", [], [RawSegment(0, 2, "iki kelime"), RawSegment(2, 5, "üç tane kelime")], [], "p", "m", None
    )
    d = b(r)
    assert all(x["start"] is None and x["end"] is None and x["confidence"] is None for x in d["words"])
    assert [s["word_range"] for s in d["segments"]] == [[0, 2], [2, 5]]
    assert not any(x["low_confidence"] for x in d["words"])


def test_build_duzensiz_kelimeler():
    r = raw([w("c", 2.0, 2.5), w("a", 0.0, 0.5), w("sıfır", 1.0, 1.0), w("b.", 0.4, 0.9), w("d", 2.2, 2.0)])
    d = b(r)
    starts = [x["start"] for x in d["words"]]
    assert starts == sorted(starts)
    assert all(x["end"] >= x["start"] for x in d["words"])
    segs = d["segments"]
    assert all(segs[i]["start"] >= segs[i - 1]["end"] for i in range(1, len(segs)))
    assert all(s["end"] >= s["start"] for s in segs)
    ws = d["words"]
    assert all(ws[i]["end"] <= ws[i + 1]["start"] for i in range(len(ws) - 1))
    assert all(s["end"] - s["start"] <= 7.0 for s in segs)


def test_build_kelime_ortusmesi_giderilir():
    d = b(raw([w("a", 0.0, 1.0), w("b", 0.5, 1.5)]))
    ws = d["words"]
    assert ws[0]["end"] == 0.5
    assert all(ws[i]["end"] <= ws[i + 1]["start"] for i in range(len(ws) - 1))


def test_dil_bos():
    d = b(raw([w("a", 0, 0.5)], language=""))
    assert d["language"] == "und"


def test_dakika_siniri():
    d = b(raw([w("a", 1, 1.5), w("b.", 60.0, 60.0)]), meta(60.0))
    assert len(d["minutes"]) == 2
    d = b(raw([w("a", 59.0, 59.99), w("b", 59.99, 60.03)]), meta(None))
    assert all(m["end"] >= m["start"] for m in d["minutes"])


def test_konusma_disi_kelime_uyarisi_ve_caller_uyarilari():
    r = raw([w("a", 1.0, 1.4, None)])
    d = b(r, vad=[NonSpeech(0.5, 2.0, "music")], warnings=[{"code": "YEDEK_MOTOR", "message": "x"}])
    assert d["words"][0]["low_confidence"] is True
    assert [x["code"] for x in d["warnings"]] == ["KONUSMA_DISI_KELIME", "YEDEK_MOTOR"]
