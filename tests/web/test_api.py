import copy
import json
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from autocript.config import Settings, load_settings
from autocript.jobs.runner import JobRunner
from autocript.jobs.store import JobStore
from autocript.types import SourceError
from autocript.web.app import create_app

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schema" / "transcript-v1.json").read_text(encoding="utf-8"))
ORNEK = json.loads((ROOT / "tests" / "fixtures" / "schema" / "ornek-v1.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _arac_yollari_geri_al(monkeypatch):
    """create_app araç yollarını modül düzeyinde ayarlar; her testten sonra eski hâline döner."""
    from autocript.audio import ffmpeg as ff

    monkeypatch.setattr(ff, "_TOOLS", None, raising=False)


def ok_work(request, on_stage, on_meta):
    on_stage("transkript")
    doc = copy.deepcopy(ORNEK)
    doc["job_id"] = request.job_id
    return doc


def build(tmp_path, work=ok_work, **kw):
    kw.setdefault("elevenlabs_api_key", "sk_test_anahtar_000000")
    s = Settings(media_dir=tmp_path / "media", **kw)
    store = JobStore(s.media_dir / "autocript.db")
    runner = JobRunner(store, work, s.media_dir, 2)
    return create_app(s, runner=runner, store=store), store, s


def upload(client, path, **data):
    with open(path, "rb") as f:
        return client.post("/api/jobs", files={"file": (path.name, f, "audio/mp4")}, data=data)


def wait_done(client, job_id):
    for _ in range(50):
        st = client.get(f"/api/jobs/{job_id}").json()
        if st["state"] in ("bitti", "hata"):
            return st
        time.sleep(0.1)
    raise AssertionError("is bitmedi")


def test_post_ve_durum(tmp_path, make_media):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = upload(client, make_media("tone", 1))
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        st = wait_done(client, job_id)
        assert st["state"] == "bitti"
        assert st["job_id"] == job_id


def test_indirmeler(tmp_path, make_media):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        job_id = upload(client, make_media("tone", 1)).json()["job_id"]
        wait_done(client, job_id)
        j = client.get(f"/api/jobs/{job_id}/transcript.json")
        assert j.status_code == 200
        assert j.headers["content-disposition"] == f'attachment; filename="transkript-{job_id}.json"'
        assert list(Draft202012Validator(SCHEMA).iter_errors(j.json())) == []
        t = client.get(f"/api/jobs/{job_id}/transcript.txt")
        assert t.headers["content-disposition"] == f'attachment; filename="transkript-{job_id}.txt"'
        assert t.text.startswith("[00:00.42] Merhaba")
        sr = client.get(f"/api/jobs/{job_id}/transcript.srt")
        assert sr.headers["content-disposition"] == f'attachment; filename="transkript-{job_id}.srt"'
        assert sr.text.startswith("1\n00:00:")


def test_bitmemis_indirme_409(tmp_path):
    app, store, s = build(tmp_path)
    store.create("j_" + "a" * 16)
    with TestClient(app) as client:
        r = client.get("/api/jobs/j_aaaaaaaaaaaaaaaa/transcript.json")
        assert r.status_code == 409
        assert set(r.json()) == {"code", "message"}


def test_yok_404(tmp_path):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/jobs/j_yokyokyokyokyoky").status_code == 404
        assert client.get("/api/jobs/j_yokyokyokyokyoky/transcript.json").status_code == 404


def test_url_alani_400(tmp_path, make_media):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = upload(client, make_media("tone", 1), url="https://youtube.com/shorts/abc")
        assert r.status_code == 400
        assert r.json() == {"code": "GECERSIZ_ISTEK", "message": "Geçersiz istek. Dosyayı ya da linki yeniden gönderin."}
        r = client.post("/api/jobs", data={"url": "https://youtube.com/shorts/abc"}, files={"x": ("x", b"y")})
        assert r.status_code == 400
        assert r.json()["code"] == "GECERSIZ_ISTEK"
        r = client.post("/api/jobs", json={"a": 1})
        assert r.status_code == 400
        assert r.json()["code"] == "GECERSIZ_ISTEK"
    assert list((s.media_dir / "jobs").glob("*")) == []


def test_buyuk_dosya_413(tmp_path, make_media):
    app, store, s = build(tmp_path, max_upload_mb=0)
    with TestClient(app) as client:
        r = upload(client, make_media("tone", 1))
        assert r.status_code == 413
        assert r.json()["code"] == "DOSYA_BUYUK"
        assert set(r.json()) == {"code", "message"}
    assert list((s.media_dir / "jobs").glob("*")) == []
    n = store._conn().execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert n == 0


def test_hata_durumu_json(tmp_path, make_media):
    def work(request, on_stage, on_meta):
        raise SourceError("VIDEO_UZUN", "Video 3 dakikadan uzun.")

    app, store, s = build(tmp_path, work=work)
    with TestClient(app) as client:
        job_id = upload(client, make_media("tone", 1)).json()["job_id"]
        st = wait_done(client, job_id)
        assert st["state"] == "hata"
        assert st["error"]["code"] == "VIDEO_UZUN"
        assert st["error"]["upload_fallback"] is True


def test_sayfa_sunuluyor(tmp_path):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert 'id="dosya"' in r.text and "app.js" in r.text
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/style.css").status_code == 200


def test_sayfa_yukleme_sinirini_sunar(tmp_path):
    app, store, s = build(tmp_path, max_upload_mb=123)
    with TestClient(app) as client:
        assert 'data-max-upload-mb="123"' in client.get("/").text


def test_uretim_baglantisi(tmp_path, make_media, monkeypatch):
    import autocript.web.app as webapp
    from autocript.stt import SttOutcome
    from autocript.types import RawTranscript, RawWord

    class FakeChain:
        def transcribe(self, audio, language):
            words = [RawWord("merhaba", 0.1, 0.5, 0.9), RawWord("dünya", 0.6, 1.0, 0.95)]
            return SttOutcome(RawTranscript("tr", "word", words, [], [], "elevenlabs", "m", None), False, None)

    monkeypatch.setattr(webapp, "build_stt_chain", lambda settings: FakeChain())
    tools = load_settings()
    s = Settings(
        elevenlabs_api_key="sk_test_anahtar_000000",
        media_dir=tmp_path / "media", nonspeech_detector="none",
        ffmpeg_bin=tools.ffmpeg_bin, ffprobe_bin=tools.ffprobe_bin,
    )
    with TestClient(webapp.create_app(s)) as client:
        job_id = upload(client, make_media("tone", 1)).json()["job_id"]
        st = wait_done(client, job_id)
        assert st["state"] == "bitti"
        assert list((s.media_dir / "jobs").glob("*")) == []
        doc = client.get(f"/api/jobs/{job_id}/transcript.json").json()
        assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == []


def test_create_app_arac_yollarini_ayarlar(tmp_path, monkeypatch):
    from autocript.audio import ffmpeg as ff

    cmds = []

    def fake_run(cmd):
        cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, b"", b"x")

    monkeypatch.setattr(ff, "_run", fake_run)
    build(tmp_path, ffmpeg_bin="X", ffprobe_bin="Y")
    with pytest.raises(SourceError):
        ff.probe(tmp_path / "a.m4a")
    with pytest.raises(SourceError):
        ff.to_flac(tmp_path / "a.m4a", tmp_path / "o.flac", check_audio=False)
    assert [c[0] for c in cmds] == ["Y", "X"]


def test_anahtar_sizmaz(tmp_path, make_media):
    def work(request, on_stage, on_meta):
        raise SourceError("STT_HATA", "Transkript motorları yanıt vermedi.", detail="HTTP 401: sk_test_SIZMASIN")

    app, store, s = build(tmp_path, work=work, elevenlabs_api_key="sk_test_SIZMASIN")
    with TestClient(app) as client:
        r = upload(client, make_media("tone", 1))
        bodies = [r.text]
        job_id = r.json()["job_id"]
        wait_done(client, job_id)
        for path in ("", "/transcript.json", "/transcript.txt", "/transcript.srt"):
            bodies.append(client.get(f"/api/jobs/{job_id}{path}").text)
        bodies.append(client.get("/").text)
        bodies.append(client.get("/static/app.js").text)
    assert all("sk_test_SIZMASIN" not in b for b in bodies)
    assert "detail" not in bodies[1]


def test_acilista_yarim_isler_hata_olur(tmp_path):
    s = Settings(media_dir=tmp_path / "media")
    store = JobStore(s.media_dir / "autocript.db")
    store.create("j_" + "b" * 16)
    app = create_app(s, runner=JobRunner(store, ok_work, s.media_dir, 1), store=store)
    with TestClient(app) as client:
        st = client.get("/api/jobs/j_bbbbbbbbbbbbbbbb").json()
        assert st["state"] == "hata"
        assert st["error"]["code"] == "SUNUCU_YENIDEN_BASLADI"


def test_temizlik_dongusu_hatada_olmez(tmp_path, monkeypatch):
    import autocript.web.app as webapp

    calls = []

    def bad_sweep(*a, **k):
        calls.append(1)
        raise OSError("yaris")

    monkeypatch.setattr(webapp, "sweep", bad_sweep)
    monkeypatch.setattr(webapp, "SWEEP_INTERVAL_S", 0.05)
    app, store, s = build(tmp_path)
    with TestClient(app):
        time.sleep(0.4)
    assert len(calls) >= 3


def test_bozuk_multipart_400(tmp_path):
    app, store, s = build(tmp_path)
    bodies = [
        b"hello world",
        b'--XX\r\nContent-Disposition: form-data; name="file"; filename="a.m4a"\r\n\r\nabc\r\n-hhh',
        b"garbage\r\n--XX\r\nxx",
    ]
    with TestClient(app) as client:
        for body in bodies:
            r = client.post(
                "/api/jobs", content=body, headers={"content-type": "multipart/form-data; boundary=XX"}
            )
            assert r.status_code == 400, body
            assert r.json()["code"] == "GECERSIZ_ISTEK"
            assert set(r.json()) == {"code", "message"}
    assert list((s.media_dir / "jobs").glob("*")) == []
    assert store._conn().execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_dosya_adsiz_file_alani_400(tmp_path):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/jobs", files={"file": (None, b"merhaba")})
        assert r.status_code == 400
        assert r.json()["code"] == "GECERSIZ_ISTEK"
    assert list((s.media_dir / "jobs").glob("*")) == []
    assert store._conn().execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_yukleme_kopunca_temizlenir(tmp_path, caplog):
    import asyncio

    app, store, s = build(tmp_path)
    head = (
        b'--XX\r\nContent-Disposition: form-data; name="file"; filename="a.m4a"\r\n'
        b"Content-Type: audio/mp4\r\n\r\n" + b"x" * 1000
    )
    messages = [
        {"type": "http.request", "body": head, "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive():
        if messages:
            return messages.pop(0)
        await asyncio.sleep(3600)

    sent = []

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": "/api/jobs", "raw_path": b"/api/jobs", "root_path": "",
        "query_string": b"", "client": ("127.0.0.1", 5000), "server": ("127.0.0.1", 8000),
        "headers": [
            (b"host", b"127.0.0.1:8000"),
            (b"content-type", b"multipart/form-data; boundary=XX"),
            (b"content-length", b"100000"),
        ],
    }
    with caplog.at_level("INFO"):
        asyncio.run(app(scope, receive, send))
    assert list((s.media_dir / "jobs").glob("*")) == []
    assert not [r for r in caplog.records if r.levelname == "ERROR"]
    assert store._conn().execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_yukleme_job_klasorune_yazilir(tmp_path, make_media):
    seen = {}

    def work(request, on_stage, on_meta):
        seen["exists"] = request.upload_path.exists()
        seen["suffix"] = request.upload_path.suffix
        seen["parent"] = request.upload_path.parent
        return ok_work(request, on_stage, on_meta)

    app, store, s = build(tmp_path, work=work)
    with TestClient(app) as client:
        job_id = upload(client, make_media("tone", 1)).json()["job_id"]
        wait_done(client, job_id)
    assert seen["exists"] and seen["suffix"] == ".m4a"
    assert seen["parent"] == s.media_dir / "jobs" / job_id


# --- Instagram link yolu (İL §6.7, §6.8) ---
IG = "https://www.instagram.com/reel/ABCDE12/"


def _isler(s):
    return list((s.media_dir / "jobs").glob("*"))


def test_link_isi_acilir(tmp_path):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/jobs", json={"url": IG})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        assert client.get(f"/api/jobs/{job_id}").status_code == 200
        wait_done(client, job_id)


def test_link_gecersiz_422(tmp_path):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/jobs", json={"url": "https://example.com/x"})
        assert r.status_code == 422
        assert r.json()["code"] == "LINK_GECERSIZ"
    assert _isler(s) == []


def test_youtube_422_kalkti(tmp_path):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/jobs", json={"url": "https://youtube.com/shorts/abcdefghijk"})
        assert r.status_code == 202
        wait_done(client, r.json()["job_id"])


def test_link_govdesi_buyuk(tmp_path):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/jobs", json={"url": "https://www.instagram.com/reel/" + "a" * 5000})
        assert r.status_code == 413
        assert r.json()["code"] == "GECERSIZ_ISTEK"
        r = client.post(
            "/api/jobs", content=b'{"url": "' + b"a" * 5000 + b'"}',
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 413
    assert _isler(s) == []


@pytest.mark.parametrize(
    "govde", [b'{"a": 1}', b'{"url": 5}', b"[]", b'"metin"', b"{bozuk", b""]
)
def test_link_govde_bicimi_400(tmp_path, govde):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/jobs", content=govde, headers={"content-type": "application/json"})
        assert r.status_code == 400
        assert r.json()["code"] == "GECERSIZ_ISTEK"
    assert _isler(s) == []


def test_link_gecersiz_kod_sira_harcamaz(tmp_path, monkeypatch):
    from autocript.sources.instapuller import InstapullerSource

    cagrilar = []
    monkeypatch.setattr(InstapullerSource, "resolve", lambda self, *a, **k: cagrilar.append(a))
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/jobs", json={"url": "https://www.instagram.com/reel/-----/"})
        assert r.status_code == 422
        assert r.json()["code"] == "LINK_GECERSIZ"
        r = client.post("/api/jobs", json={"url": "https://youtube.com/watch?v=kisa"})
        assert r.status_code == 422
        assert r.json()["code"] == "LINK_GECERSIZ"
    assert cagrilar == []
    assert _isler(s) == []


def test_link_origin_yabanci_403(tmp_path):
    from autocript.yerel.guvenlik import Oturum, cookie_name

    oturum = Oturum(token="T" * 43, port=8000)
    s = Settings(media_dir=tmp_path / "media", elevenlabs_api_key="sk_test_anahtar_000000")
    store = JobStore(s.media_dir / "autocript.db")
    runner = JobRunner(store, ok_work, s.media_dir, 1)
    app = create_app(s, runner=runner, store=store, oturum=oturum)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        c.cookies.set(cookie_name(8000), oturum.token)
        r = c.post("/api/jobs", json={"url": IG}, headers={"Origin": "https://kotu.example"})
        assert r.status_code == 403
        assert r.json()["code"] == "GECERSIZ_KAYNAK"
    assert _isler(s) == []


def test_link_kurulum_gerekli(tmp_path):
    app, store, s = build(tmp_path, elevenlabs_api_key=None)
    with TestClient(app) as client:
        r = client.post("/api/jobs", json={"url": IG})
        assert r.status_code == 409
    assert _isler(s) == []


def test_yukleme_bicim_disi_415(tmp_path):
    app, store, s = build(tmp_path)
    dosya = tmp_path / "not.txt"
    dosya.write_bytes(b"merhaba" * 100)
    with TestClient(app) as client:
        r = client.post("/api/jobs", files={"file": ("not.txt", dosya.read_bytes(), "text/plain")})
        assert r.status_code == 415
        assert r.json()["code"] == "DOSYA_BICIMI"
        r = client.post("/api/jobs", files={"file": ("uzantisiz", b"abc", "audio/mp4")})
        assert r.status_code == 415
    assert _isler(s) == []


@pytest.mark.parametrize("ad", ["a.MP4", "b.m4a", "c.webm"])
def test_yukleme_bicimleri_kabul(tmp_path, ad):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/jobs", files={"file": (ad, b"abc", "application/octet-stream")})
        assert r.status_code == 202
        wait_done(client, r.json()["job_id"])


def test_sayfa_bicim_listesi(tmp_path):
    import re

    from autocript.config import UPLOAD_EXTS

    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text
    assert "__UPLOAD_EXTS__" not in html
    m = re.search(r'id="dosya"[^>]*accept="([^"]*)"', html)
    assert m and m.group(1) == ",".join(UPLOAD_EXTS)
