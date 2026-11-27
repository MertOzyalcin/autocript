import json
from pathlib import Path

from jsonschema import Draft202012Validator

from autocript.config import Settings
from autocript.jobs.pipeline import make_detector, run_pipeline
from autocript.nonspeech.null import NullDetector
from autocript.nonspeech.silero import SileroDetector
from autocript.sources.upload import UploadSource
from autocript.stt import SttOutcome
from autocript.types import JobRequest, RawTranscript, RawWord, SourceError

SCHEMA = json.loads((Path(__file__).parents[2] / "schema" / "transcript-v1.json").read_text("utf-8"))


class FakeChain:
    def __init__(self, words, used_fallback=False, provider="elevenlabs", primary_code="STT_HATA"):
        self.words, self.used_fallback, self.provider = words, used_fallback, provider
        self.primary_code = primary_code
        self.calls = []

    def transcribe(self, audio, language):
        self.calls.append((audio, language))
        raw = RawTranscript("tr", "word", self.words, [], [], self.provider, "m", None)
        err = SourceError(self.primary_code, "x") if self.used_fallback else None
        return SttOutcome(raw, self.used_fallback, err)


WORDS = [RawWord("merhaba", 0.1, 0.5, 0.9), RawWord("dünya", 0.6, 1.0, 0.95)]


def _run(make_media, tmp_path, chain, kind="tone", secs=2):
    p = make_media(kind, secs)
    req = JobRequest("j1", tmp_path, None, p)
    stages, metas = [], []
    doc = run_pipeline(
        req, source=UploadSource(185), stt=chain, detector=NullDetector(),
        low_conf_threshold=0.8, on_stage=stages.append, on_meta=metas.append,
    )
    return doc, stages, metas


def test_pipeline_asamalar(make_media, tmp_path):
    chain = FakeChain(WORDS)
    doc, stages, metas = _run(make_media, tmp_path, chain)
    assert stages == ["kaynak", "ses", "transkript", "son"]
    assert len(metas) == 1 and metas[0].kind == "upload"
    assert doc["source"]["kind"] == "upload"
    Draft202012Validator(SCHEMA).validate(doc)
    assert chain.calls == [(tmp_path / "audio.flac", None)]


def test_pipeline_yedek_uyarisi(make_media, tmp_path):
    doc, _, _ = _run(make_media, tmp_path, FakeChain(WORDS, True, "groq"))
    assert [w["code"] for w in doc["warnings"]] == ["YEDEK_MOTOR"]
    assert doc["engine"]["provider"] == "groq"
    Draft202012Validator(SCHEMA).validate(doc)


def test_pipeline_anahtar_reddi_iki_uyari(make_media, tmp_path):
    chain = FakeChain(WORDS, True, "groq", primary_code="ANAHTAR_REDDEDILDI")
    doc, _, _ = _run(make_media, tmp_path, chain)
    assert [w["code"] for w in doc["warnings"]] == ["ANAHTAR_REDDEDILDI", "YEDEK_MOTOR"]
    assert doc["warnings"][0]["message"] == (
        "ElevenLabs anahtarın reddedildi; Anahtarlar sayfasından kontrol et. "
        "Bu transkript yedek motor Groq ile yapıldı, güven bilgisi yok."
    )
    Draft202012Validator(SCHEMA).validate(doc)


def test_pipeline_sessiz(make_media, tmp_path):
    doc, _, _ = _run(make_media, tmp_path, FakeChain([]), kind="silence", secs=3)
    assert any(w["code"] == "KONUSMA_YOK" for w in doc["warnings"])


def test_pipeline_tek_probe(make_media, tmp_path, monkeypatch):
    import autocript.audio.ffmpeg as ff
    import autocript.sources.upload as up

    calls = []
    real = ff.probe

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(ff, "probe", counting)
    monkeypatch.setattr(up, "probe", counting)
    _run(make_media, tmp_path, FakeChain(WORDS))
    assert len(calls) == 1


def test_make_detector():
    assert isinstance(make_detector(Settings(nonspeech_detector="none")), NullDetector)
    assert isinstance(make_detector(Settings(nonspeech_detector="silero")), SileroDetector)


# --- resolve_source / transcribe_result ---

import pytest  # noqa: E402

from autocript.jobs.pipeline import resolve_source  # noqa: E402
from autocript.types import SourceMeta, SourceResult  # noqa: E402


class FakeUpload:
    def __init__(self, result):
        self.result, self.calls = result, []

    def resolve(self, request):
        self.calls.append(request)
        return self.result


class FakeLink:
    def __init__(self, result, stages=("sira", "kaynak")):
        self.result, self.stages, self.calls = result, stages, []

    def resolve(self, request, on_stage):
        self.calls.append(request)
        for s in self.stages:
            on_stage(s)
        return self.result


def _sonuc(kind="upload"):
    meta = SourceMeta(kind=kind, url=None, platform_id=None, title="t", author=None,
                      published_at=None, duration_s=1.0)
    return SourceResult(meta=meta, audio_path=None, transcript=None)


IG = "https://www.instagram.com/reel/x/"


def test_resolve_source_secici(tmp_path):
    up_sonuc, ig_sonuc = _sonuc("upload"), _sonuc("instagram")
    up, ig = FakeUpload(up_sonuc), FakeLink(ig_sonuc)
    metas = []

    r = resolve_source(JobRequest("j1", tmp_path, None, tmp_path / "v.mp4"), upload=up,
                       link=ig, on_stage=lambda s: None, on_meta=metas.append)
    assert r is up_sonuc and len(up.calls) == 1 and not ig.calls

    r = resolve_source(JobRequest("j1", tmp_path, IG, None),
                       upload=up, link=ig, on_stage=lambda s: None, on_meta=metas.append)
    assert r is ig_sonuc and len(ig.calls) == 1
    assert metas == [up_sonuc.meta, ig_sonuc.meta]

    with pytest.raises(SourceError) as e:
        resolve_source(JobRequest("j1", tmp_path, IG, None),
                       upload=up, link=None, on_stage=lambda s: None, on_meta=None)
    assert e.value.code == "IG_ARAC_YOK"


def test_resolve_source_kaynak_asamasi(tmp_path):
    stages = []
    resolve_source(JobRequest("j1", tmp_path, None, tmp_path / "v.mp4"),
                   upload=FakeUpload(_sonuc()), link=None, on_stage=stages.append,
                   on_meta=None)
    assert stages == ["kaynak"]

    stages = []
    resolve_source(JobRequest("j1", tmp_path, IG, None),
                   upload=FakeUpload(_sonuc()), link=FakeLink(_sonuc("instagram")),
                   on_stage=stages.append, on_meta=None)
    assert stages == ["sira", "kaynak"]  # resolve_source kendisi "kaynak" eklemez
