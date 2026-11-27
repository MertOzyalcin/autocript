"""Link (Instagram ve YouTube) uçtan uca testleri: gerçek create_app, gerçek runner, sahte instapuller, gerçek saat."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import autocript.web.app as webapp
from autocript.config import Settings, load_settings
from autocript.metinler import hata_metni
from autocript.stt import SttOutcome
from autocript.types import RawTranscript, RawWord

ROOT = Path(__file__).resolve().parents[2]
SAHTE_SRC = ROOT / "tests" / "fixtures" / "sahte_instapuller"
SCHEMA = json.loads((ROOT / "schema" / "transcript-v1.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _arac_yollari_geri_al(monkeypatch):
    from autocript.audio import ffmpeg as ff

    monkeypatch.setattr(ff, "_TOOLS", None, raising=False)


class _SahteZincir:
    def transcribe(self, audio, language):
        words = [
            RawWord("merhaba", 0.1, 0.5, 0.92),
            RawWord("dünya.", 0.6, 1.0, 0.95),
        ]
        raw = RawTranscript("tr", "word", words, [], [], "elevenlabs", "scribe_v3", None)
        return SttOutcome(raw, False, None)


def _ayarlar(tmp_path: Path, ffprobe_yolu: str) -> Settings:
    araclar = load_settings()
    qjs = tmp_path / "qjs.exe"
    qjs.write_bytes(b"")  # conftest koruması gerçek qjs'yi kapatır; ön kontrol için boş dosya yeter
    return Settings(
        elevenlabs_api_key="sk_test_anahtar_000000",
        media_dir=tmp_path / "media",
        nonspeech_detector="none",
        ffmpeg_bin=araclar.ffmpeg_bin,
        ffprobe_bin=ffprobe_yolu,
        instapuller_python=sys.executable,
        instapuller_src=str(SAHTE_SRC),
        instapuller_state_dir=tmp_path / "state",
        js_runtime_bin=str(qjs),
    )


def _gunluk_oku(yol: Path) -> list[dict]:
    if not yol.exists():
        return []
    return [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines() if s.strip()]


@pytest.mark.slow
def test_uc_link_15sn_arayla_biter(tmp_path, monkeypatch, ffprobe_yolu, make_media):
    """3 Instagram linki >= 15 sn arayla biter, sıra görünür, dosya yükleme önce biter."""
    video = make_media("tone", 2, video_codec="h264")
    ses = make_media("tone", 1)
    gunluk = tmp_path / "cagrilar.jsonl"

    monkeypatch.setenv("SAHTE_IP_SENARYO", "ok")
    monkeypatch.setenv("SAHTE_IP_VIDEO", str(video))
    monkeypatch.setenv("SAHTE_IP_LOG", str(gunluk))
    # 2 sn gecikme: ilk Instagram işi çalışırken yükleme işinin ondan önce bitmesini kararlı kılar.
    monkeypatch.setenv("SAHTE_IP_GECIKME_S", "2.0")
    monkeypatch.setattr(webapp, "build_stt_chain", lambda settings: _SahteZincir())

    ayar = _ayarlar(tmp_path, ffprobe_yolu)
    with TestClient(webapp.create_app(ayar)) as client:
        link_idler = []
        for kod in ("REEL001", "REEL002", "REEL003"):
            r = client.post("/api/jobs", json={"url": f"https://www.instagram.com/reel/{kod}/"})
            assert r.status_code == 202
            link_idler.append(r.json()["job_id"])

        with open(ses, "rb") as f:
            r_up = client.post("/api/jobs", files={"file": (ses.name, f, "audio/mp4")})
        assert r_up.status_code == 202
        yukleme_id = r_up.json()["job_id"]

        tum_idler = link_idler + [yukleme_id]
        bitis_zamani: dict[str, float] = {}
        sira_goruldu = False
        son = time.monotonic() + 90.0

        while len(bitis_zamani) < len(tum_idler) and time.monotonic() < son:
            for jid in tum_idler:
                if jid in bitis_zamani:
                    continue
                st = client.get(f"/api/jobs/{jid}").json()
                assert st["state"] != "hata", f"beklenmeyen hata ({jid}): {st}"
                if jid in link_idler and st.get("stage") == "sira":
                    sira_goruldu = True
                if st["state"] == "bitti":
                    bitis_zamani[jid] = time.monotonic()
            if len(bitis_zamani) < len(tum_idler):
                time.sleep(0.1)

        assert set(bitis_zamani) == set(tum_idler), f"90 sn içinde bitmeyen işler: {set(tum_idler) - set(bitis_zamani)}"
        assert sira_goruldu, "bekleyen Instagram işlerinden hiçbiri 'sira' aşamasını göstermedi"
        assert bitis_zamani[yukleme_id] < min(bitis_zamani[j] for j in link_idler), (
            "dosya yüklemesi ilk Instagram işinden önce bitmedi"
        )

        for jid in link_idler:
            doc = client.get(f"/api/jobs/{jid}/transcript.json").json()
            assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == []
            assert doc["source"]["kind"] == "instagram"

    kayitlar = _gunluk_oku(gunluk)
    assert len(kayitlar) == 3, f"tam 3 sahte instapuller çağrısı bekleniyordu, olan: {len(kayitlar)}"
    for i in (1, 2):
        aralik = kayitlar[i]["start"] - kayitlar[i - 1]["end"]
        assert aralik >= 14.9, f"çağrı {i} ile {i - 1} arası {aralik:.2f} sn (< 14.9)"

    assert list((ayar.media_dir / "jobs").glob("*")) == []


def test_link_hata_kutusu_akisi(tmp_path, monkeypatch, ffprobe_yolu):
    """IG_ERISILEMEDI senaryosunda iş hata olur; mesaj tablodan, upload_fallback True, url dolu."""
    gunluk = tmp_path / "cagrilar.jsonl"
    monkeypatch.setenv("SAHTE_IP_SENARYO", "hata:IG_ERISILEMEDI")
    monkeypatch.setenv("SAHTE_IP_LOG", str(gunluk))
    monkeypatch.setattr(webapp, "build_stt_chain", lambda settings: _SahteZincir())

    ayar = _ayarlar(tmp_path, ffprobe_yolu)
    with TestClient(webapp.create_app(ayar)) as client:
        r = client.post("/api/jobs", json={"url": "https://www.instagram.com/reel/GIZLI01/?igsh=xyz"})
        assert r.status_code == 202
        job_id = r.json()["job_id"]

        st = None
        for _ in range(100):
            st = client.get(f"/api/jobs/{job_id}").json()
            if st["state"] in ("bitti", "hata"):
                break
            time.sleep(0.1)

    assert st is not None and st["state"] == "hata"
    err = st["error"]
    assert err["code"] == "IG_ERISILEMEDI"
    assert err["message"] == hata_metni("IG_ERISILEMEDI", "tr")
    assert err["upload_fallback"] is True
    assert err["url"] == "https://www.instagram.com/reel/GIZLI01/"
    assert "detail" not in err
    assert "SAHTE MESAJ" not in json.dumps(st, ensure_ascii=False)
    assert len(_gunluk_oku(gunluk)) == 1
    assert list((ayar.media_dir / "jobs").glob("*")) == []


def _bekle(client, job_id, sn=60):
    st = None
    for _ in range(sn * 10):
        st = client.get(f"/api/jobs/{job_id}").json()
        if st["state"] in ("bitti", "hata"):
            break
        time.sleep(0.1)
    return st


def test_youtube_shorts_transkript(tmp_path, monkeypatch, ffprobe_yolu, make_media):
    """YouTube Shorts: ses (.m4a) iner, hattan geçer, meta.kind youtube, iş klasörü silinir."""
    ses = make_media("tone", 2)  # yalnızca ses: .m4a
    monkeypatch.setenv("SAHTE_IP_SENARYO", "ok")
    monkeypatch.setenv("SAHTE_IP_VIDEO", str(ses))
    monkeypatch.setattr(webapp, "build_stt_chain", lambda settings: _SahteZincir())

    ayar = _ayarlar(tmp_path, ffprobe_yolu)
    with TestClient(webapp.create_app(ayar)) as client:
        r = client.post("/api/jobs", json={"url": "https://www.youtube.com/shorts/abcdefghijk?feature=share"})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        st = _bekle(client, job_id)
        assert st["state"] == "bitti", st
        doc = client.get(f"/api/jobs/{job_id}/transcript.json").json()
        assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == []
        assert doc["source"]["kind"] == "youtube"
        assert doc["source"]["url"] == "https://www.youtube.com/watch?v=abcdefghijk"
    assert list((ayar.media_dir / "jobs").glob("*")) == []


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_instapuller_mesaji_sizmaz(tmp_path, monkeypatch, ffprobe_yolu, dil):
    """instapuller'ın message/detail alanı ve stderr'i ekrana (API yanıtına) sızmaz."""
    monkeypatch.setenv("SAHTE_IP_SENARYO", "hata:IG_ERISILEMEDI")
    monkeypatch.setenv("SAHTE_IP_MESAJ", "SIZINTI-MSG")
    monkeypatch.setenv("SAHTE_IP_DETAY", "SIZINTI-DETAY")
    monkeypatch.setenv("SAHTE_IP_STDERR", "SIZINTI-STDERR")
    monkeypatch.setattr(webapp, "build_stt_chain", lambda settings: _SahteZincir())

    ayar = _ayarlar(tmp_path, ffprobe_yolu)
    with TestClient(webapp.create_app(ayar)) as client:
        r = client.post(
            "/api/jobs", json={"url": "https://youtu.be/abcdefghijk?si=x"}, headers={"Cookie": f"dil={dil}"}
        )
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        for _ in range(100):
            ham = client.get(f"/api/jobs/{job_id}", headers={"Cookie": f"dil={dil}"})
            st = ham.json()
            if st["state"] in ("bitti", "hata"):
                break
            time.sleep(0.1)
    assert st["state"] == "hata"
    assert st["error"]["code"] == "IG_ERISILEMEDI"
    assert st["error"]["message"] == hata_metni("IG_ERISILEMEDI", dil, {"site": "youtube"})
    assert "YouTube" in st["error"]["message"]
    assert st["error"]["upload_fallback"] is True
    for sizinti in ("SIZINTI-MSG", "SIZINTI-DETAY", "SIZINTI-STDERR"):
        assert sizinti not in ham.text


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_js_ortami_yoksa_instapuller_cagrilmaz(tmp_path, monkeypatch, ffprobe_yolu, make_media, dil):
    """JS ortamı yok: YouTube işi JS_ORTAMI_YOK ile biter, instapuller çağrılmaz; Instagram çalışır."""
    gunluk = tmp_path / "cagrilar.jsonl"
    video = make_media("tone", 2, video_codec="h264")
    monkeypatch.setenv("SAHTE_IP_SENARYO", "ok")
    monkeypatch.setenv("SAHTE_IP_VIDEO", str(video))
    monkeypatch.setenv("SAHTE_IP_LOG", str(gunluk))
    monkeypatch.setattr(webapp, "build_stt_chain", lambda settings: _SahteZincir())

    ayar = _ayarlar(tmp_path, ffprobe_yolu)
    ayar.js_runtime_bin = str(tmp_path / "yok" / "qjs.exe")
    basliklar = {"Cookie": f"dil={dil}"}
    with TestClient(webapp.create_app(ayar)) as client:
        r = client.post("/api/jobs", json={"url": "https://www.youtube.com/shorts/abcdefghijk"}, headers=basliklar)
        assert r.status_code == 202
        yt = client.get(f"/api/jobs/{r.json()['job_id']}", headers=basliklar).json()
        for _ in range(100):
            if yt["state"] in ("bitti", "hata"):
                break
            time.sleep(0.1)
            yt = client.get(f"/api/jobs/{r.json()['job_id']}", headers=basliklar).json()
        assert yt["state"] == "hata"
        assert yt["error"]["code"] == "JS_ORTAMI_YOK"
        assert yt["error"]["upload_fallback"] is True
        assert "YouTube" in yt["error"]["message"]
        assert _gunluk_oku(gunluk) == []

        r2 = client.post("/api/jobs", json={"url": "https://www.instagram.com/reel/REEL001/"})
        assert r2.status_code == 202
        ig = _bekle(client, r2.json()["job_id"])
        assert ig["state"] == "bitti", ig
    assert len(_gunluk_oku(gunluk)) == 1


@pytest.mark.slow
def test_instagram_ve_youtube_birbirini_beklemez(tmp_path, monkeypatch, ffprobe_yolu, make_media):
    """Instagram ve YouTube art arda: ikincisi 15 sn beklemez; aynı siteden iki link >= 15 sn arayla."""
    video = make_media("tone", 2, video_codec="h264")
    gunluk = tmp_path / "cagrilar.jsonl"
    monkeypatch.setenv("SAHTE_IP_SENARYO", "ok")
    monkeypatch.setenv("SAHTE_IP_VIDEO", str(video))
    monkeypatch.setenv("SAHTE_IP_LOG", str(gunluk))
    monkeypatch.setattr(webapp, "build_stt_chain", lambda settings: _SahteZincir())

    ayar = _ayarlar(tmp_path, ffprobe_yolu)
    with TestClient(webapp.create_app(ayar)) as client:
        idler = []
        for url in (
            "https://www.instagram.com/reel/REEL001/",
            "https://www.youtube.com/shorts/abcdefghijk",
            "https://www.youtube.com/shorts/bcdefghijkl",
        ):
            r = client.post("/api/jobs", json={"url": url})
            assert r.status_code == 202
            idler.append(r.json()["job_id"])
        for jid in idler:
            assert _bekle(client, jid, sn=90)["state"] == "bitti"

    k = {x["url"]: x for x in _gunluk_oku(gunluk)}
    assert len(k) == 3
    ig = k["https://www.instagram.com/reel/REEL001/"]
    yt1 = k["https://www.youtube.com/watch?v=abcdefghijk"]
    yt2 = k["https://www.youtube.com/watch?v=bcdefghijkl"]
    # Instagram, YouTube'u 15 sn bekletmedi: ilk YouTube çağrısı Instagram'ın bitişinden hemen sonra.
    assert yt1["start"] - ig["start"] < 10.0
    assert yt2["start"] - yt1["end"] >= 14.9


@pytest.mark.slow
def test_kabul_akisi_iki_site_iki_dil(tmp_path, monkeypatch, ffprobe_yolu, make_media):
    """KT2 Task 10 Step 1: Reel + Shorts art arda biter (iki dilde okunur), sonra YouTube hatası EN."""
    ses = make_media("tone", 2)  # instapuller YouTube'da yalnızca ses indirir (.m4a)
    monkeypatch.setenv("SAHTE_IP_SENARYO", "ok")
    monkeypatch.setenv("SAHTE_IP_VIDEO", str(ses))
    monkeypatch.setattr(webapp, "build_stt_chain", lambda settings: _SahteZincir())

    ayar = _ayarlar(tmp_path, ffprobe_yolu)
    with TestClient(webapp.create_app(ayar)) as client:
        reel = client.post("/api/jobs", json={"url": "https://www.instagram.com/reel/REEL001/"},
                           headers={"Cookie": "dil=tr"})
        shorts = client.post("/api/jobs", json={"url": "https://youtube.com/shorts/abcdefghijk?feature=share"},
                             headers={"Cookie": "dil=en"})
        assert (reel.status_code, shorts.status_code) == (202, 202)
        beklenen = {reel.json()["job_id"]: "instagram", shorts.json()["job_id"]: "youtube"}
        for jid, site in beklenen.items():
            assert _bekle(client, jid, sn=90)["state"] == "bitti"
            for dil in ("tr", "en"):
                st = client.get(f"/api/jobs/{jid}", headers={"Cookie": f"dil={dil}"}).json()
                assert st["state"] == "bitti"
                doc = client.get(f"/api/jobs/{jid}/transcript.json", headers={"Cookie": f"dil={dil}"}).json()
                assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == []
                assert doc["source"]["kind"] == site
    assert list((ayar.media_dir / "jobs").glob("*")) == []

    # Aynı uygulama ayarlarıyla YouTube hatası: İngilizce mesaj, dosya yüklemeye yönlendirme.
    monkeypatch.setenv("SAHTE_IP_SENARYO", "hata:IG_RATE_LIMIT")
    with TestClient(webapp.create_app(ayar)) as client:
        r = client.post("/api/jobs", json={"url": "https://youtu.be/bcdefghijkl"}, headers={"Cookie": "dil=en"})
        assert r.status_code == 202
        jid = r.json()["job_id"]
        _bekle(client, jid, sn=90)
        en = client.get(f"/api/jobs/{jid}", headers={"Cookie": "dil=en"}).json()
        tr = client.get(f"/api/jobs/{jid}", headers={"Cookie": "dil=tr"}).json()
    assert en["state"] == "hata"
    assert en["error"]["code"] == "IG_RATE_LIMIT"
    assert en["error"]["message"] == "YouTube is limiting requests right now. Try again later, or upload the video as a file."
    assert en["error"]["upload_fallback"] is True
    assert tr["error"]["message"].startswith("YouTube şu an istekleri sınırlıyor")
