"""Hata kodları, yedek yol bayrakları ve instapuller kod eşlemesi (KT2, F1 §6.4).

Bu dosyayı yalnızca mimar değiştirir. Mesaj metinleri `autocript/metinler/*.json`
kataloğundadır; instapuller'ın `message` ve `upload_fallback` alanları kullanılmaz.
`IG_` önekli kodlar tarihseldir ve YouTube için de kullanılır (KT2 kararı 3).
"""

from __future__ import annotations

from autocript.metinler import hata_metni
from autocript.types import SourceError

# kod -> upload_fallback (plandaki tablonun "Yedek" sütunu)
FALLBACK: dict[str, bool] = {
    "LINK_GECERSIZ": True,
    "IG_ERISILEMEDI": True,
    "IG_RATE_LIMIT": True,
    "IG_ARAC_GUNCEL_DEGIL": True,
    "IG_VIDEO_DEGIL": True,
    "IG_ARAC_YOK": True,
    # instapuller v0.3.0 (Task 7): YouTube JS çalışma ortamı yok ya da JS sınaması çözülemedi.
    "JS_ORTAMI_YOK": True,
    "KAYNAK_GECICI": True,
    "DOSYA_BUYUK": True,
    "VIDEO_UZUN": True,
    "DOSYA_BOZUK": True,
    "DOSYA_SES_YOK": True,
    "DOSYA_BICIMI": True,
    "FFPROBE_YOK": False,
    "STT_HATA": True,
    "ANAHTAR_REDDEDILDI": False,
    "SUNUCU_YENIDEN_BASLADI": True,
    "BEKLENMEYEN_HATA": False,
    "GECERSIZ_ISTEK": False,
    "KURULUM_GEREKLI": False,
    "IS_YOK": False,
    "IS_BITMEDI": False,
    "GECERSIZ_HOST": False,
    "GECERSIZ_KAYNAK": False,
    "OTURUM_YOK": False,
}

# instapuller v0.3.0 README'sindeki 15 kod -> autocript kodu (Task 7 sözleşme kaydı)
INSTAPULLER_KODLARI: dict[str, str] = {
    "LINK_GECERSIZ": "LINK_GECERSIZ",
    "IG_ERISILEMEDI": "IG_ERISILEMEDI",
    "IG_RATE_LIMIT": "IG_RATE_LIMIT",
    "IG_ARAC_GUNCEL_DEGIL": "IG_ARAC_GUNCEL_DEGIL",
    "IG_VIDEO_DEGIL": "IG_VIDEO_DEGIL",
    "IG_COOLDOWN": "KAYNAK_GECICI",
    "DOSYA_BUYUK": "DOSYA_BUYUK",
    "VIDEO_UZUN": "VIDEO_UZUN",
    "DOSYA_BOZUK": "DOSYA_BOZUK",
    "KAYNAK_GECICI": "KAYNAK_GECICI",
    "JS_ORTAMI_YOK": "JS_ORTAMI_YOK",
    "FFPROBE_YOK": "FFPROBE_YOK",
    "ARG_GECERSIZ": "BEKLENMEYEN_HATA",
    "SILME_HATASI": "BEKLENMEYEN_HATA",
    "BEKLENMEYEN_HATA": "BEKLENMEYEN_HATA",
}


def hata(
    kod: str,
    detail: str | None = None,
    *,
    site: str | None = None,
    varyant: str | None = None,
) -> SourceError:
    """Katalogdaki Türkçe mesajla SourceError üretir. Bilinmeyen kod BEKLENMEYEN_HATA olur."""
    if kod not in FALLBACK:
        kod = "BEKLENMEYEN_HATA"
    params = {"site": site} if site else None
    return SourceError(
        kod,
        hata_metni(kod, "tr", params, varyant),
        upload_fallback=FALLBACK[kod],
        detail=detail,
        params=params,
        varyant=varyant,
    )
