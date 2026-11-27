import pytest

from autocript.sources.upload import UploadSource
from autocript.types import JobRequest, SourceError


def _req(path, tmp_path):
    return JobRequest(job_id="j1", work_dir=tmp_path, url=None, upload_path=path)


def test_upload_ses_yok(make_media, tmp_path):
    p = make_media("tone", 1, audio=False)
    with pytest.raises(SourceError) as e:
        UploadSource(185).resolve(_req(p, tmp_path))
    assert e.value.code == "DOSYA_SES_YOK"


def test_upload_bozuk(tmp_path):
    p = tmp_path / "x.mp4"
    p.write_bytes(b"\x00\x13rastgele baytlar" * 50)
    with pytest.raises(SourceError) as e:
        UploadSource(185).resolve(_req(p, tmp_path))
    assert e.value.code == "DOSYA_BOZUK"


def test_upload_sure_sinirlari(make_media, tmp_path):
    r = UploadSource(2.0).resolve(_req(make_media("silence", 2.0), tmp_path))
    assert r.meta.kind == "upload"
    assert r.meta.duration_s == pytest.approx(2.0, abs=0.1)
    assert r.audio_path is not None and r.transcript is None
    assert r.meta.url is None and r.meta.title is None
    assert r.meta.stats == {"views": None, "likes": None, "comments": None}
    with pytest.raises(SourceError) as e:
        UploadSource(2.0).resolve(_req(make_media("silence", 2.1), tmp_path))
    assert e.value.code == "VIDEO_UZUN"
    assert "3 dakikayı aşıyor" in e.value.message
    UploadSource(185).resolve(_req(make_media("tone", 0.5), tmp_path))


def test_upload_sure_iki_ondalik(tmp_path, monkeypatch):
    import autocript.sources.upload as up
    from autocript.types import ProbeResult

    monkeypatch.setattr(up, "probe", lambda p: ProbeResult(47.023311, True, "mp4"))
    r = UploadSource(185).resolve(_req(tmp_path / "x.mp4", tmp_path))
    assert r.meta.duration_s == 47.02
