import copy
import logging

import httpx
from fastapi.testclient import TestClient

from autocript.config import Settings
from autocript.jobs.runner import JobRunner
from autocript.jobs.store import JobStore
from autocript.web.app import create_app
from autocript.yerel.guvenlik import Oturum, cookie_name

from .test_api import ORNEK, upload, wait_done

KEY = "sk_0123456789abcdefa3f9"
KEY2 = "sk_ZZZZZZZZZZZZZZZZb7c1"
GKEY = "gsk_0123456789abcdefg4h5"
HATA = "ElevenLabs anahtarı zorunlu."
SABIT_GECERSIZ = "Anahtar geçersiz. Tamamını kopyaladığınızdan emin olun."


def kur(tmp_path, env_text=None, handler=None, **kw):
    env = tmp_path / ".env"
    if env_text is not None:
        env.write_text(env_text, encoding="utf-8")
    s = Settings(media_dir=tmp_path / "media", **kw)
    store = JobStore(s.media_dir / "autocript.db")

    def work(request, on_stage, on_meta):
        doc = copy.deepcopy(ORNEK)
        doc["job_id"] = request.job_id
        return doc

    runner = JobRunner(store, work, s.media_dir, 2)
    transport = httpx.MockTransport(handler) if handler else None
    app = create_app(s, runner=runner, store=store, env_path=env, http_transport=transport)
    return app, s, env


def test_kurulum_get_maskeli(tmp_path):
    app, s, env = kur(tmp_path, elevenlabs_api_key=KEY)
    with TestClient(app) as c:
        r = c.get("/api/kurulum")
        assert r.status_code == 200
        assert r.json() == {
            "elevenlabs": {"set": True, "masked": "sk_…a3f9"},
            "groq": {"set": False, "masked": None},
        }
        assert KEY not in r.text


def test_kurulum_put_kaydeder_ve_maskeler(tmp_path):
    app, s, env = kur(tmp_path, "YOUTUBE_API_KEY=y\n")
    with TestClient(app) as c:
        r = c.put("/api/kurulum", json={"elevenlabs": "  " + KEY + "\n"})
        assert r.status_code == 200
        assert KEY not in r.text
        assert r.json()["elevenlabs"] == {"set": True, "masked": "sk_…a3f9"}
    lines = env.read_text(encoding="utf-8").splitlines()
    assert "YOUTUBE_API_KEY=y" in lines
    assert f"ELEVENLABS_API_KEY={KEY}" in lines
    assert s.elevenlabs_api_key == KEY


def test_kurulum_put_groq_bos_siler(tmp_path):
    app, s, env = kur(tmp_path, f"GROQ_API_KEY={GKEY}\n", elevenlabs_api_key=KEY, groq_api_key=GKEY)
    with TestClient(app) as c:
        r = c.put("/api/kurulum", json={"groq": ""})
        assert r.status_code == 200
        assert r.json()["groq"] == {"set": False, "masked": None}
    assert "GROQ_API_KEY" not in env.read_text(encoding="utf-8")
    assert s.groq_api_key is None


def test_kurulum_put_elevenlabs_bos_400(tmp_path):
    app, s, env = kur(tmp_path, elevenlabs_api_key=KEY)
    with TestClient(app) as c:
        r = c.put("/api/kurulum", json={"elevenlabs": ""})
        assert r.status_code == 400
        assert r.json() == {"code": "GECERSIZ_ISTEK", "message": HATA}
    assert s.elevenlabs_api_key == KEY


def test_kurulum_put_gecersiz_400(tmp_path):
    ilk = f"ELEVENLABS_API_KEY={KEY}\n"
    app, s, env = kur(tmp_path, ilk, elevenlabs_api_key=KEY)
    with TestClient(app) as c:
        r = c.put("/api/kurulum", json={"groq": GKEY, "elevenlabs": KEY2 + "\nGROQ_API_KEY=x"})
        assert r.status_code == 400
        assert r.json()["code"] == "GECERSIZ_ISTEK"
        assert r.json()["message"] == "Anahtar biçimi tanınmadı."
        assert c.put("/api/kurulum", json={"bilinmeyen": KEY}).status_code == 400
        assert c.put("/api/kurulum", json={"groq": 5}).status_code == 400
    assert env.read_text(encoding="utf-8") == ilk
    assert s.groq_api_key is None and s.elevenlabs_api_key == KEY


def test_kurulum_put_elevenlabs_eksik_400(tmp_path):
    app, s, env = kur(tmp_path)
    with TestClient(app) as c:
        for body in ({}, {"groq": GKEY}):
            r = c.put("/api/kurulum", json=body)
            assert r.status_code == 400
            assert r.json()["message"] == HATA
    assert not env.exists()
    assert s.groq_api_key is None


def test_kurulum_put_yalniz_groq_korur(tmp_path):
    app, s, env = kur(tmp_path, elevenlabs_api_key=KEY)
    with TestClient(app) as c:
        assert c.put("/api/kurulum", json={"groq": GKEY}).status_code == 200
        assert s.elevenlabs_api_key == KEY and s.groq_api_key == GKEY
        assert c.put("/api/kurulum", json={"elevenlabs": KEY2}).status_code == 200
        assert s.elevenlabs_api_key == KEY2 and s.groq_api_key == GKEY


def test_kurulum_test_kayitli_anahtar(tmp_path):
    gorulen = []

    def handler(request):
        gorulen.append(request.headers.get("xi-api-key"))
        return httpx.Response(200, json={})

    app, s, env = kur(tmp_path, handler=handler, elevenlabs_api_key=KEY)
    with TestClient(app) as c:
        r = c.post("/api/kurulum/test", json={"provider": "elevenlabs"})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert KEY not in r.text
        r = c.post("/api/kurulum/test", json={"provider": "elevenlabs", "key": "   "})
        assert r.json()["ok"] is True
    assert gorulen == [KEY, KEY]


def test_kurulum_test_kayit_yok(tmp_path):
    app, s, env = kur(tmp_path, handler=lambda r: httpx.Response(200))
    with TestClient(app) as c:
        r = c.post("/api/kurulum/test", json={"provider": "groq"})
        assert r.json() == {"ok": False, "message": "Önce anahtarı yapıştırın."}
        assert c.post("/api/kurulum/test", json={"provider": "x"}).status_code == 400


def test_kurulum_test_kirpilir(tmp_path):
    gorulen = []

    def handler(request):
        gorulen.append(request.headers.get("xi-api-key"))
        return httpx.Response(200, json={})

    app, s, env = kur(tmp_path, handler=handler)
    with TestClient(app) as c:
        r = c.post("/api/kurulum/test", json={"provider": "elevenlabs", "key": "  " + KEY + "\n"})
        assert r.json()["ok"] is True
    assert gorulen == [KEY]


def test_kurulum_test_bicimsiz(tmp_path):
    cagri = []
    app, s, env = kur(tmp_path, handler=lambda r: cagri.append(r) or httpx.Response(200))
    with TestClient(app) as c:
        for k in (KEY + "\nX=1", "sk_ " + "a" * 20):
            r = c.post("/api/kurulum/test", json={"provider": "elevenlabs", "key": k})
            assert r.status_code == 200
            assert r.json() == {"ok": False, "message": SABIT_GECERSIZ}
    assert cagri == []


def test_kurulum_test_gecersiz(tmp_path):
    app, s, env = kur(
        tmp_path, handler=lambda r: httpx.Response(401, json={"detail": {"status": "invalid_api_key"}})
    )
    with TestClient(app) as c:
        r = c.post("/api/kurulum/test", json={"provider": "elevenlabs", "key": KEY})
        assert r.json() == {"ok": False, "message": SABIT_GECERSIZ}


def test_anahtarsiz_is_409(tmp_path, make_media):
    app, s, env = kur(tmp_path)
    with TestClient(app) as c:
        r = upload(c, make_media("tone", 1))
        assert r.status_code == 409
        assert r.json() == {"code": "KURULUM_GEREKLI", "message": "Önce ElevenLabs anahtarını girin."}


def test_anasayfa_kuruluma_yonlendirir(tmp_path):
    app, s, env = kur(tmp_path)
    with TestClient(app) as c:
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/kurulum"
        assert c.get("/kurulum").status_code == 200
        assert c.get("/api/saglik").json() == {"ok": True}
    (tmp_path / "b").mkdir()
    app, s, env = kur(tmp_path / "b", elevenlabs_api_key=KEY)
    with TestClient(app) as c:
        assert c.get("/", follow_redirects=False).status_code == 200


def test_kayittan_sonra_zincir_yenilenir(tmp_path, monkeypatch, make_media):
    import autocript.web.app as webapp
    from autocript.stt import SttOutcome
    from autocript.types import RawTranscript, RawWord

    sayac = []

    class FakeChain:
        def transcribe(self, audio, language):
            words = [RawWord("merhaba", 0.1, 0.5, 0.9)]
            return SttOutcome(RawTranscript("tr", "word", words, [], [], "elevenlabs", "m", None), False, None)

    monkeypatch.setattr(webapp, "build_stt_chain", lambda settings: sayac.append(1) or FakeChain())
    s = Settings(media_dir=tmp_path / "media", nonspeech_detector="none")
    with TestClient(create_app(s, env_path=tmp_path / ".env")) as c:
        assert sayac == []
        assert c.put("/api/kurulum", json={"elevenlabs": KEY}).status_code == 200
        r = upload(c, make_media("tone", 1))
        assert r.status_code == 202
        wait_done(c, r.json()["job_id"])
    assert len(sayac) == 1


def test_koruma_uygulamada(tmp_path):
    oturum = Oturum(token="T" * 43, port=8000)
    s = Settings(media_dir=tmp_path / "media", elevenlabs_api_key=KEY)
    store = JobStore(s.media_dir / "autocript.db")
    runner = JobRunner(store, lambda *a: None, s.media_dir, 1)
    app = create_app(s, runner=runner, store=store, oturum=oturum, env_path=tmp_path / ".env")
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        assert c.get("/api/kurulum").status_code == 401
        assert c.get("/api/kurulum", headers={"Host": "evil.com"}).status_code == 400
        assert c.get("/?t=" + oturum.token, follow_redirects=False).status_code == 303
        assert c.cookies.get(cookie_name(8000)) == oturum.token
        r = c.put("/api/kurulum", json={"groq": GKEY}, headers={"Origin": "http://127.0.0.1:8000"})
        assert r.status_code == 200
        assert c.put("/api/kurulum", json={"groq": GKEY}).status_code == 403


def test_anahtar_hicbir_yanitta_yok(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    app, s, env = kur(tmp_path, handler=lambda r: httpx.Response(200, json={}))
    yanitlar = []
    with TestClient(app) as c:
        yanitlar.append(c.get("/api/kurulum"))
        yanitlar.append(c.put("/api/kurulum", json={"elevenlabs": KEY, "groq": GKEY}))
        yanitlar.append(c.get("/api/kurulum"))
        yanitlar.append(c.post("/api/kurulum/test", json={"provider": "elevenlabs"}))
        yanitlar.append(c.post("/api/kurulum/test", json={"provider": "groq", "key": GKEY}))
        yanitlar.append(c.put("/api/kurulum", json={"elevenlabs": KEY2 + "\n"}))
        yanitlar.append(c.put("/api/kurulum", json={"groq": ""}))
        yanitlar.append(c.get("/kurulum"))
        yanitlar.append(c.get("/"))
    for r in yanitlar:
        metin = r.text + str(dict(r.headers))
        for k in (KEY, KEY2, GKEY):
            assert k not in metin
    for k in (KEY, KEY2, GKEY):
        assert k not in caplog.text


def test_eski_env_satirlari_yok_sayilir(tmp_path):
    eski = "GEMINI_API_KEY=g\nYOUTUBE_API_KEY=y\nGEMINI_MODELS=a\n"
    app, s, env = kur(tmp_path, eski)
    with TestClient(app) as c:
        r = c.get("/api/kurulum")
        assert set(r.json()) == {"elevenlabs", "groq"}
        r = c.put("/api/kurulum", json={"elevenlabs": KEY})
        assert r.status_code == 200
        assert set(r.json()) == {"elevenlabs", "groq"}
    lines = env.read_text(encoding="utf-8").splitlines()
    for satir in ("GEMINI_API_KEY=g", "YOUTUBE_API_KEY=y", "GEMINI_MODELS=a"):
        assert satir in lines
