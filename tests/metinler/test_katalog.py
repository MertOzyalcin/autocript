import json
import re
from pathlib import Path

import pytest

from autocript.metinler import (
    dil_sec,
    hata_metni,
    istek_dili,
    konsol_dili,
    katalog_ui,
    metin,
    uyari_metni,
    yerellestir_hata,
)

KLASOR = Path(__file__).resolve().parents[2] / "autocript" / "metinler"
KOD = Path(__file__).resolve().parents[2] / "autocript"


def _yukle(dil: str) -> dict[str, str]:
    return json.loads((KLASOR / f"{dil}.json").read_text(encoding="utf-8"))


def test_iki_dil_ayni_anahtarlar():
    tr, en = _yukle("tr"), _yukle("en")
    assert set(tr) == set(en)
    assert all(v.strip() for v in [*tr.values(), *en.values()])


def test_yer_tutucular_esit():
    tr, en = _yukle("tr"), _yukle("en")
    for k in tr:
        assert set(re.findall(r"\{(\w+)\}", tr[k])) == set(re.findall(r"\{(\w+)\}", en[k])), k


def test_tablo_kelimesi_kelimesine():
    beklenen = {
        "hata.LINK_GECERSIZ": (
            "Bu link tanınmadı. YouTube Shorts ya da Instagram Reel linki girin ya da videoyu dosya olarak yükleyin.",
            "This link wasn't recognized. Enter a YouTube Shorts or Instagram Reel link, or upload the video as a file.",
        ),
        "hata.IG_ERISILEMEDI": (
            "Bu videoya erişilemedi. Video gizli ya da silinmiş olabilir, ya da {site} giriş istiyor olabilir. Videoyu dosya olarak yükleyin.",
            "This video couldn't be accessed. It may be private or deleted, or {site} may require a login. Upload the video as a file instead.",
        ),
        "hata.KAYNAK_GECICI": (
            "{site}'a şu an ulaşılamadı. Biraz sonra yeniden deneyin ya da videoyu dosya olarak yükleyin.",
            "Couldn't reach {site} right now. Try again shortly, or upload the video as a file.",
        ),
        "hata.DOSYA_BUYUK.yukleme": ("Dosya 500 MB'ı aşıyor.", "The file is larger than 500 MB."),
        "uyari.YEDEK_MOTOR": (
            "ElevenLabs yanıt vermedi; Groq kullanıldı, güven bilgisi yok.",
            "ElevenLabs didn't respond, so Groq was used; there is no confidence data.",
        ),
        "kurulum.AG": (
            "Sağlayıcıya ulaşılamadı. İnternet bağlantınızı kontrol edin.",
            "Couldn't reach the provider. Check your internet connection.",
        ),
    }
    tr, en = _yukle("tr"), _yukle("en")
    for k, (t, e) in beklenen.items():
        assert (tr[k], en[k]) == (t, e), k


def test_site_yerlesir():
    assert hata_metni("KAYNAK_GECICI", "tr", {"site": "youtube"}) == (
        "YouTube'a şu an ulaşılamadı. Biraz sonra yeniden deneyin ya da videoyu dosya olarak yükleyin."
    )
    assert hata_metni("KAYNAK_GECICI", "en", {"site": "youtube"}).startswith("Couldn't reach YouTube right now.")
    # site verilmezse KT2 öncesi işler gibi Instagram
    assert hata_metni("IG_RATE_LIMIT", "tr").startswith("Instagram şu an")


def test_varyant_ve_geri_dusme():
    assert hata_metni("DOSYA_BUYUK", "en", varyant="yukleme") == "The file is larger than 500 MB."
    assert hata_metni("DOSYA_BUYUK", "tr", varyant="yok") == metin("hata.DOSYA_BUYUK", "tr")
    assert hata_metni("XYZ", "en") == "Something unexpected went wrong."
    assert metin("ui.olmayan", "en") == "ui.olmayan"


def test_saglayici_ve_bicimler():
    assert hata_metni("ANAHTAR_REDDEDILDI", "en", {"provider": "Groq"}).startswith("The Groq key")
    assert hata_metni("DOSYA_BICIMI", "tr").endswith("Desteklenenler: MP4, MOV, M4V, WEBM, MKV, AVI, 3GP, MP3, M4A, AAC, WAV, FLAC, OGG, OPUS, WMA.")


@pytest.mark.parametrize("deger,beklenen", [(None, "tr"), ("", "tr"), ("de", "tr"), ("EN", "tr"), ("en", "en"), ("tr", "tr")])
def test_dil_sec(deger, beklenen):
    assert dil_sec(deger) == beklenen


def test_istek_dili_scope_ve_bozuk_cerez():
    scope = {"headers": [(b"cookie", b"oturum=abc; dil=en")]}
    assert istek_dili(scope) == "en"
    assert istek_dili({"headers": [(b"cookie", b'dil="; bozuk')]}) == "tr"
    assert istek_dili({"headers": []}) == "tr"


def test_yerellestir_hata_kopya():
    err = {"code": "IG_RATE_LIMIT", "message": "eski", "upload_fallback": True, "params": {"site": "youtube"}}
    out = yerellestir_hata(err, "en")
    assert out["message"].startswith("YouTube is limiting")
    assert err["message"] == "eski"


def test_uyari_ve_ui():
    assert uyari_metni("KONUSMA_YOK", "en") == "No speech was found in the video."
    assert all(k.startswith(("ui.", "site.")) for k in katalog_ui("en"))


def test_kodda_gecen_her_kod_katalogda():
    tr = _yukle("tr")
    desen = re.compile(r'(?:hata\(|SourceError\(|"code":\s*)\s*"([A-Z][A-Z_]+)"')
    kodlar: set[str] = set()
    for p in KOD.rglob("*.py"):
        metin_ = p.read_text(encoding="utf-8")
        kodlar |= set(desen.findall(metin_))
        m = re.search(r"_MESAJLAR = \{(.*?)\}", metin_, re.S)
        if m:
            kodlar |= set(re.findall(r'"([A-Z_]+)":', m.group(1)))
    assert kodlar, "tarama boş"
    eksik = {k for k in kodlar if f"hata.{k}" not in tr and f"uyari.{k}" not in tr}
    assert not eksik


def test_mesajlarda_teknik_terim_yok():
    for dil in ("tr", "en"):
        for k, v in _yukle(dil).items():
            if k.startswith("hata."):
                for terim in ("yt-dlp", "ffprobe", "JSON", "stderr", "instapuller"):
                    assert terim not in v, (dil, k)


def test_konsol_anahtarlari_iki_dilde_ayni_yer_tutucularla():
    tr, en = _yukle("tr"), _yukle("en")
    anahtarlar = {k for k in tr if k.startswith("konsol.")}
    assert anahtarlar, "konsol.* anahtarı yok"
    assert anahtarlar == {k for k in en if k.startswith("konsol.")}
    for k in anahtarlar:
        assert set(re.findall(r"\{(\w+)\}", tr[k])) == set(re.findall(r"\{(\w+)\}", en[k])), k


@pytest.mark.parametrize("deger,beklenen", [("tr", "tr"), ("en", "en"), ("de", "tr"), ("EN", "tr")])
def test_konsol_dili_ortam_degiskeni(monkeypatch, deger, beklenen):
    # tr/en dışı değer dil_sec gibi tr'ye düşer; baslat.cmd değeri zaten normalleştirir.
    monkeypatch.setenv("AUTOCRIPT_KONSOL_DIL", deger)
    assert konsol_dili() == beklenen


@pytest.mark.parametrize("deger", [None, ""])
def test_konsol_dili_algilama_tr_ya_da_en(monkeypatch, deger):
    if deger is None:
        monkeypatch.delenv("AUTOCRIPT_KONSOL_DIL", raising=False)
    else:
        monkeypatch.setenv("AUTOCRIPT_KONSOL_DIL", deger)
    assert konsol_dili() in {"tr", "en"}


def test_konsol_dili_windows_disi_algilama(monkeypatch):
    import sys

    from autocript import metinler

    monkeypatch.delenv("AUTOCRIPT_KONSOL_DIL", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    def patla():
        raise RuntimeError

    monkeypatch.setattr(metinler.locale, "getlocale", patla)
    assert konsol_dili() == "en"
    monkeypatch.setattr(metinler.locale, "getlocale", lambda: ("Turkish_Türkiye", "cp1254"))
    assert konsol_dili() == "tr"
    monkeypatch.setattr(metinler.locale, "getlocale", lambda: ("en_US", "UTF-8"))
    assert konsol_dili() == "en"


def _baglanti_kalan(metin_: str) -> list[str]:
    """Link anlamında 'bağlantı' kullanımı (KT2 ek 2). 'İnternet bağlantı…' kalıbı istisnadır."""
    t = metin_.replace("İ", "i").lower()
    t = re.sub(r"internet\s+bağlant[ıi]", "", t)
    return re.findall(r"bağlant[ıi]\w*", t)


def test_turkce_link_terimi():
    tr = json.loads((KLASOR / "tr.json").read_text(encoding="utf-8"))
    for anahtar, deger in tr.items():
        assert _baglanti_kalan(deger) == [], f"{anahtar}: 'bağlantı' yerine 'link' kullanılmalı"
    static = KOD / "web" / "static"
    for ad in ("index.html", "kurulum.html", "app.js", "kurulum.js"):
        icerik = (static / ad).read_text(encoding="utf-8")
        assert _baglanti_kalan(icerik) == [], ad
