from autocript.config import ROOT, load_settings
from autocript.types import SourceError


def test_source_error_alanlari():
    e = SourceError("LINK_GECERSIZ", "x")
    assert e.code == "LINK_GECERSIZ"
    assert e.message == "x"
    assert e.upload_fallback is True
    assert e.detail is None
    assert str(e) == "LINK_GECERSIZ: x"


def test_source_error_detail():
    e = SourceError("STT_HATA", "Sağlayıcı hata verdi", detail="HTTP 400: {...}")
    assert e.detail == "HTTP 400: {...}"
    assert str(e) == "STT_HATA: Sağlayıcı hata verdi | HTTP 400: {...}"


def _temiz_ortam(monkeypatch):
    for k in (
        "ELEVENLABS_API_KEY", "GROQ_API_KEY", "FFMPEG_BIN", "FFPROBE_BIN",
    ):
        monkeypatch.delenv(k, raising=False)


def test_settings_eksik_anahtar_none(monkeypatch, tmp_path):
    _temiz_ortam(monkeypatch)
    monkeypatch.setattr("autocript.config.ROOT", tmp_path)  # proje içi ffmpeg yokken yalın ad
    s = load_settings(env_file=None)
    assert s.groq_api_key is None
    assert s.ffmpeg_bin == "ffmpeg"


def test_settings_ortamdan_okur(monkeypatch):
    _temiz_ortam(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "  anahtar  ")
    s = load_settings(env_file=None)
    assert s.groq_api_key == "anahtar"


def test_settings_goreli_arac_yolu_koke_baglanir(monkeypatch):
    _temiz_ortam(monkeypatch)
    monkeypatch.setenv("FFMPEG_BIN", "tools/ffmpeg/bin/ffmpeg.exe")
    s = load_settings(env_file=None)
    assert s.ffmpeg_bin == str(ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe")


def test_settings_env_dosyasi(monkeypatch, tmp_path):
    _temiz_ortam(monkeypatch)
    f = tmp_path / ".env"
    f.write_text("GROQ_API_KEY=dosyadan\n", encoding="utf-8")
    assert load_settings(env_file=f).groq_api_key == "dosyadan"
    monkeypatch.setenv("GROQ_API_KEY", "ortamdan")
    assert load_settings(env_file=f).groq_api_key == "ortamdan"


_YENI = (
    "STT_TIMEOUT_S", "LOW_CONFIDENCE_THRESHOLD", "NONSPEECH_DETECTOR", "MEDIA_DIR",
    "MAX_UPLOAD_MB", "MAX_DURATION_S", "JOB_CONCURRENCY",
)


def test_settings_yeni_alanlar(monkeypatch):
    _temiz_ortam(monkeypatch)
    for k in _YENI:
        monkeypatch.delenv(k, raising=False)
    s = load_settings(env_file=None)
    assert s.stt_timeout_s == 60.0
    assert s.low_confidence_threshold == 0.80
    assert s.nonspeech_detector == "none"
    assert s.media_dir == ROOT / "data" / "media"
    assert s.max_upload_mb == 500
    assert s.max_duration_s == 185.0
    assert s.job_concurrency == 3


def test_settings_yeni_alanlar_ortamdan(monkeypatch, tmp_path):
    _temiz_ortam(monkeypatch)
    monkeypatch.setenv("STT_TIMEOUT_S", "5")
    monkeypatch.setenv("LOW_CONFIDENCE_THRESHOLD", "0.5")
    monkeypatch.setenv("NONSPEECH_DETECTOR", "silero")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("MAX_DURATION_S", "2")
    monkeypatch.setenv("JOB_CONCURRENCY", "1")
    s = load_settings(env_file=None)
    assert (s.stt_timeout_s, s.low_confidence_threshold, s.nonspeech_detector) == (5.0, 0.5, "silero")
    assert (s.media_dir, s.max_upload_mb, s.max_duration_s, s.job_concurrency) == (tmp_path, 1, 2.0, 1)


def test_settings_nonspeech_gecersiz(monkeypatch):
    import pytest

    _temiz_ortam(monkeypatch)
    monkeypatch.setenv("NONSPEECH_DETECTOR", "foo")
    with pytest.raises(ValueError):
        load_settings(env_file=None)


def test_stt_outcome():
    from autocript.stt import SttOutcome
    from autocript.types import RawTranscript

    raw = RawTranscript("tr", "word", [], [], [], "groq", "whisper-large-v3", None)
    o = SttOutcome(raw=raw, used_fallback=True, primary_error=SourceError("STT_HATA", "x"))
    assert o.used_fallback and o.primary_error.code == "STT_HATA"


def test_jobstatus_sira_asamasi():
    import dataclasses

    from autocript.types import JobRequest, JobStatus

    st = JobStatus(job_id="j", state="calisiyor", stage="sira", error=None, meta=None,
                   created_at="a", updated_at="b")
    assert st.stage == "sira"
    assert {f.name for f in dataclasses.fields(JobRequest)} == {"job_id", "work_dir", "url", "upload_path"}
