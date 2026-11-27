import json
from pathlib import Path

from autocript.config import UPLOAD_EXTS
from autocript.metinler import hata_metni
from autocript.sources.hatalar import FALLBACK, INSTAPULLER_KODLARI, hata

_TR = json.loads(
    (Path(__file__).resolve().parents[2] / "autocript" / "metinler" / "tr.json").read_text(encoding="utf-8")
)


def test_kod_tablosu_kapsar():
    # instapuller v0.3.0 README "Error Codes" tablosunun tam kümesi (15 kod).
    assert set(INSTAPULLER_KODLARI) == {
        "LINK_GECERSIZ", "IG_ERISILEMEDI", "IG_RATE_LIMIT", "IG_ARAC_GUNCEL_DEGIL", "IG_VIDEO_DEGIL",
        "IG_COOLDOWN", "DOSYA_BUYUK", "VIDEO_UZUN", "DOSYA_BOZUK", "KAYNAK_GECICI", "JS_ORTAMI_YOK",
        "FFPROBE_YOK", "ARG_GECERSIZ", "SILME_HATASI", "BEKLENMEYEN_HATA",
    }
    assert all(v in FALLBACK for v in INSTAPULLER_KODLARI.values())
    assert INSTAPULLER_KODLARI["IG_COOLDOWN"] == "KAYNAK_GECICI"
    assert INSTAPULLER_KODLARI["ARG_GECERSIZ"] == INSTAPULLER_KODLARI["SILME_HATASI"] == "BEKLENMEYEN_HATA"


def test_fallback_katalogla_ayni_kume():
    assert {f"hata.{k}" for k in FALLBACK} == {k for k in _TR if k.startswith("hata.") and k.count(".") == 1}


def test_fallback_degerleri():
    hayir = {
        "FFPROBE_YOK", "ANAHTAR_REDDEDILDI", "BEKLENMEYEN_HATA", "GECERSIZ_ISTEK", "KURULUM_GEREKLI",
        "IS_YOK", "IS_BITMEDI", "GECERSIZ_HOST", "GECERSIZ_KAYNAK", "OTURUM_YOK",
    }
    for kod, fb in FALLBACK.items():
        assert fb is (kod not in hayir), kod


def test_youtube_henuz_yok_kalkti():
    assert "YOUTUBE_HENUZ_YOK" not in FALLBACK
    assert hata("YOUTUBE_HENUZ_YOK").code == "BEKLENMEYEN_HATA"
    klasor = Path(__file__).resolve().parents[2] / "autocript" / "metinler"
    for dil in ("tr", "en"):
        kat = json.loads((klasor / f"{dil}.json").read_text(encoding="utf-8"))
        assert "hata.YOUTUBE_HENUZ_YOK" not in kat


def test_js_ortami_yok():
    assert INSTAPULLER_KODLARI["JS_ORTAMI_YOK"] == "JS_ORTAMI_YOK"
    assert FALLBACK["JS_ORTAMI_YOK"] is True
    assert "YouTube" in hata_metni("JS_ORTAMI_YOK", "en")
    assert "YouTube" in hata("JS_ORTAMI_YOK", site="youtube").message


def test_bilinmeyen_kod_beklenmeyen():
    e = hata("XYZ", detail="d")
    assert (e.code, e.upload_fallback, e.detail) == ("BEKLENMEYEN_HATA", False, "d")


def test_hata_site_ve_varyant_tasir():
    e = hata("KAYNAK_GECICI", site="youtube")
    assert e.params == {"site": "youtube"}
    assert e.message == hata_metni("KAYNAK_GECICI", "tr", {"site": "youtube"})
    assert e.message.startswith("YouTube'a")
    v = hata("DOSYA_BUYUK", varyant="yukleme")
    assert (v.varyant, v.message, v.params) == ("yukleme", "Dosya 500 MB'ı aşıyor.", None)


def test_upload_exts():
    assert len(UPLOAD_EXTS) == 15
    assert all(e.startswith(".") and e == e.lower() for e in UPLOAD_EXTS)
