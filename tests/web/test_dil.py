"""Sunucu tarafı dil (KT2 Task 5): hata, uyarı, kurulum, güvenlik ve TXT etiketleri çerezin dilinde."""

import ast
import copy
import json
import re
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from autocript.config import Settings
from autocript.jobs.runner import JobRunner
from autocript.jobs.store import JobStore
from autocript.metinler import hata_metni, uyari_metni
from autocript.sources.hatalar import hata
from autocript.stt._errors import stt_error
from autocript.web.app import create_app
from autocript.yerel.guvenlik import Oturum

from .test_api import ORNEK, SCHEMA, ok_work, upload, wait_done

KEY = "sk_0123456789abcdefa3f9"
IG_URL = "https://www.instagram.com/reel/ABCdef12345/"
EN = {"Cookie": "dil=en"}
TR = {"Cookie": "dil=tr"}


def kur(tmp_path, work=ok_work, handler=None, **kw):
    kw.setdefault("elevenlabs_api_key", KEY)
    s = Settings(media_dir=tmp_path / "media", **kw)
    store = JobStore(s.media_dir / "autocript.db")
    runner = JobRunner(store, work, s.media_dir, 2)
    transport = httpx.MockTransport(handler) if handler else None
    app = create_app(
        s, runner=runner, store=store, env_path=tmp_path / ".env", http_transport=transport
    )
    return app, store, s


def test_varsayilan_turkce(tmp_path):
    app, _, _ = kur(tmp_path)
    with TestClient(app) as c:
        r = c.post("/api/jobs", json={"url": "x"})
        assert r.status_code == 422
        assert r.json()["code"] == "LINK_GECERSIZ"
        assert r.json()["message"] == hata_metni("LINK_GECERSIZ", "tr")
        assert r.json()["message"].startswith("Bu link tanınmadı.")


def test_ingilizce_cerez(tmp_path):
    app, _, _ = kur(tmp_path)
    with TestClient(app) as c:
        r = c.post("/api/jobs", json={"url": "x"}, headers=EN)
        assert r.status_code == 422
        assert r.json()["message"] == hata_metni("LINK_GECERSIZ", "en")
        assert r.json()["message"].startswith("This link wasn't recognized.")
        r = c.post("/api/jobs", json={"url": "x"}, headers={"Cookie": "dil=xx"})
        assert r.json()["message"] == hata_metni("LINK_GECERSIZ", "tr")


def test_is_hatasi_dile_gore(tmp_path):
    def work(request, on_stage, on_meta):
        raise hata("IG_RATE_LIMIT", detail="429", site="instagram")

    app, store, _ = kur(tmp_path, work=work)
    with TestClient(app) as c:
        job_id = c.post("/api/jobs", json={"url": IG_URL}).json()["job_id"]
        wait_done(c, job_id)
        tr = c.get(f"/api/jobs/{job_id}", headers=TR).json()["error"]
        en = c.get(f"/api/jobs/{job_id}", headers=EN).json()["error"]
    assert tr["message"].startswith("Instagram şu an istekleri sınırlıyor")
    assert en["message"].startswith("Instagram is limiting requests right now")
    assert tr["code"] == en["code"] == "IG_RATE_LIMIT"
    assert tr["params"] == {"site": "instagram"}
    assert "varyant" not in tr
    # Veritabanındaki ham kayıt Türkçe kalır.
    assert store.get(job_id).error["message"] == hata_metni("IG_RATE_LIMIT", "tr", {"site": "instagram"})


def test_uyari_dile_gore(tmp_path):
    def work(request, on_stage, on_meta):
        doc = copy.deepcopy(ORNEK)
        doc["job_id"] = request.job_id
        doc["warnings"] = [{"code": "YEDEK_MOTOR", "message": uyari_metni("YEDEK_MOTOR", "tr")}]
        return doc

    app, store, _ = kur(tmp_path, work=work)
    with TestClient(app) as c:
        job_id = c.post("/api/jobs", json={"url": IG_URL}).json()["job_id"]
        wait_done(c, job_id)
        en = c.get(f"/api/jobs/{job_id}/transcript.json", headers=EN)
        tr = c.get(f"/api/jobs/{job_id}/transcript.json", headers=TR)
    d_en, d_tr = json.loads(en.text), json.loads(tr.text)
    assert d_en["warnings"][0]["message"] == uyari_metni("YEDEK_MOTOR", "en")
    assert d_tr["warnings"][0]["message"] == uyari_metni("YEDEK_MOTOR", "tr")
    assert d_en["warnings"][0]["message"] != d_tr["warnings"][0]["message"]
    d_en["warnings"][0]["message"] = d_tr["warnings"][0]["message"]
    assert json.dumps(d_en, ensure_ascii=False, indent=2) == tr.text
    assert list(Draft202012Validator(SCHEMA).iter_errors(json.loads(en.text))) == []
    # Saklanan belge değişmez.
    assert store.get_transcript(job_id)["warnings"][0]["message"] == uyari_metni("YEDEK_MOTOR", "tr")


def test_kurulum_dile_gore(tmp_path):
    app, _, _ = kur(tmp_path, handler=lambda r: httpx.Response(401, json={"detail": "x"}))
    with TestClient(app) as c:
        r = c.put("/api/kurulum", json={"elevenlabs": ""}, headers=EN)
        assert r.status_code == 400
        assert r.json() == {"code": "GECERSIZ_ISTEK", "message": "The ElevenLabs key is required."}
        r = c.put("/api/kurulum", json={"elevenlabs": ""}, headers=TR)
        assert r.json()["message"] == "ElevenLabs anahtarı zorunlu."
        r = c.post("/api/kurulum/test", json={"provider": "elevenlabs", "key": KEY}, headers=EN)
        assert r.json() == {
            "ok": False,
            "message": "The key is invalid. Make sure you copied all of it.",
        }
        r = c.post("/api/kurulum/test", json={"provider": "elevenlabs", "key": KEY}, headers=TR)
        assert r.json()["message"] == "Anahtar geçersiz. Tamamını kopyaladığınızdan emin olun."


def test_guvenlik_dile_gore(tmp_path):
    oturum = Oturum(token="T" * 43, port=8000)
    app = create_app(
        Settings(media_dir=tmp_path / "m2", elevenlabs_api_key=KEY), oturum=oturum
    )
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        r = c.get("/api/kurulum", headers=EN)
        assert r.status_code == 401
        assert r.json() == {
            "code": "OTURUM_YOK",
            "message": "No session. Open the app with baslat.cmd.",
        }
        assert c.get("/api/kurulum").json()["message"] == hata_metni("OTURUM_YOK", "tr")
        r = c.get("/", headers=EN)
        assert r.status_code == 401
        assert '<html lang="en">' in r.text
        assert hata_metni("OTURUM_YOK", "en") in r.text
        r = c.get("/")
        assert '<html lang="tr">' in r.text
        assert hata_metni("OTURUM_YOK", "tr") in r.text
        r = c.get("/api/kurulum", headers={"Host": "evil.com", **EN})
        assert r.json()["message"] == hata_metni("GECERSIZ_HOST", "en")


def test_anahtar_reddi_saglayici_adi(tmp_path, make_media):
    def work(request, on_stage, on_meta):
        resp = httpx.Response(401, text="no", request=httpx.Request("POST", "http://x"))
        raise stt_error("ElevenLabs", httpx.HTTPStatusError("x", request=resp.request, response=resp), [])

    app, store, _ = kur(tmp_path, work=work)
    with TestClient(app) as c:
        job_id = upload(c, make_media("tone", 1)).json()["job_id"]
        wait_done(c, job_id)
        err = c.get(f"/api/jobs/{job_id}", headers=EN).json()["error"]
    assert err["code"] == "ANAHTAR_REDDEDILDI"
    assert err["params"] == {"provider": "ElevenLabs"}
    assert err["message"] == (
        "The ElevenLabs key was rejected or has run out of credit. Check it on the Keys page."
    )


def test_yukleme_hatasi_varyanti(tmp_path):
    app, _, _ = kur(tmp_path, max_upload_mb=1)
    with TestClient(app) as c:
        r = c.post(
            "/api/jobs",
            files={"file": ("a.mp4", b"x" * (2 * 1024 * 1024), "video/mp4")},
            headers=EN,
        )
        assert r.status_code == 413
        assert r.json()["message"] == hata_metni("DOSYA_BUYUK", "en", None, "yukleme")
        r = c.post("/api/jobs", files={"file": ("a.exe", b"x", "x/y")}, headers=EN)
        assert r.status_code == 415
        assert r.json()["message"] == hata_metni("DOSYA_BICIMI", "en")


def test_txt_etiket_dile_gore(tmp_path):
    def work(request, on_stage, on_meta):
        doc = copy.deepcopy(ORNEK)
        doc["job_id"] = request.job_id
        doc["non_speech"] = [{"start": 12.0, "end": 18.5, "kind": "music"}]
        return doc

    app, _, _ = kur(tmp_path, work=work)
    with TestClient(app) as c:
        job_id = c.post("/api/jobs", json={"url": IG_URL}).json()["job_id"]
        wait_done(c, job_id)
        en = c.get(f"/api/jobs/{job_id}/transcript.txt", headers=EN).text
        tr = c.get(f"/api/jobs/{job_id}/transcript.txt", headers=TR).text
        srt = c.get(f"/api/jobs/{job_id}/transcript.srt", headers=EN)
    assert re.search(r"^\[00:12\.00\] \[music\]$", en, re.M)
    assert re.search(r"^\[00:12\.00\] \[müzik\]$", tr, re.M)
    assert srt.status_code == 200


# --- Katalog dışı Türkçe sabit kalmadı ---

KOD = Path(__file__).resolve().parents[2] / "autocript"
_TR = re.compile("[çğıöşüÇĞİÖŞÜ]")
# Yanıta girmeyen, açıkça izinli tek tek sabitler: (dosya, sabitin başı).
_IZIN = {
    ("metinler/__init__.py", ""),
    # Sağlayıcının İngilizce/Türkçe "müzik" olay metnini eşleştirir; çıktıya girmez.
    ("stt/elevenlabs.py", "müzik"),
    # make_detector: baslat.cmd'nin yakaladığı kurulum hatası (plan: izinli).
    # instapuller kurulumunun iç nedenleri: yalnızca "(details: ...)" satırında, sistem
    # diliyle ilgisiz teknik ayrıntı olarak görünür; etiketi yerelleştirilmiştir.
    ("yerel/araclar.py", "mutlak ya da geçersiz yol"),
    ("yerel/araclar.py", "beklenmeyen arşiv yolu"),
    ("yerel/araclar.py", "arşiv yolu dışarı çıkıyor"),
    ("yerel/araclar.py", "arşiv boş"),
    ("yerel/araclar.py", "uv sync çıkış kodu"),
    ("jobs/pipeline.py", "Konuşmasız bölüm dedektörü kurulu değil"),
}
_LOG = {"debug", "info", "warning", "error", "exception", "critical"}


def _izinli_ata(node, parents) -> bool:
    """Günlük çağrısı, detail= argümanı ya da iç ValueError/RuntimeError mesajı."""
    n = node
    while n in parents:
        p = parents[n]
        if isinstance(p, ast.Call):
            f = p.func
            if isinstance(f, ast.Attribute) and f.attr in _LOG:
                return True
            if isinstance(f, ast.Name) and f.id in {"ValueError", "RuntimeError", "OSError"}:
                return True
        if isinstance(p, ast.keyword) and p.arg == "detail":
            return True
        n = p
    return False


def _detay_degiskeni(node, parents) -> bool:
    """`ayrinti = ...` gibi yalnızca detail=/günlük için kurulan yerel değişkenler."""
    n = node
    while n in parents:
        p = parents[n]
        if isinstance(p, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in {"detay", "ayrinti", "detail"} for t in p.targets
        ):
            return True
        n = p
    return False


def test_yanitta_turkce_sabit_kalmadi():
    kalan = []
    for p in sorted(KOD.rglob("*.py")):
        rel = p.relative_to(KOD).as_posix()
        tree = ast.parse(p.read_text(encoding="utf-8"))
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Constant) and isinstance(n.value, str) and _TR.search(n.value)):
                continue
            if isinstance(parents.get(n), ast.Expr):  # docstring
                continue
            if _izinli_ata(n, parents) or _detay_degiskeni(n, parents):
                continue
            if any(rel == f and n.value.startswith(b) for f, b in _IZIN):
                continue
            kalan.append(f"{rel}:{n.lineno}: {n.value[:60]!r}")
    assert kalan == []
