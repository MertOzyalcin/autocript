"""İki dilli metin kataloğu (KT2 kararları 5-6).

Kullanıcıya görünen bütün sunucu metinleri `tr.json` ve `en.json` dosyalarından gelir.
Hata ve uyarılar kod + parametre olarak saklanır; metin yanıt anında isteğin diliyle üretilir.
Katalog dosyalarını yalnızca mimar değiştirir (`ui.*` anahtarları hariç).
"""

from __future__ import annotations

import json
import locale
import os
import sys
from functools import cache
from http.cookies import SimpleCookie
from pathlib import Path

DILLER: tuple[str, ...] = ("tr", "en")
VARSAYILAN_DIL = "tr"
DIL_CEREZI = "dil"

_KLASOR = Path(__file__).resolve().parent

# {site} ve {provider} verilmezse kullanılan değerler. KT2 öncesinde saklanan link işleri
# yalnızca Instagram'dı; STT anahtar hatası yalnızca ElevenLabs/Groq'tan gelir.
_VARSAYILAN_DEGISKEN = {"site": "instagram", "provider": "ElevenLabs"}


@cache
def _katalog(dil: str) -> dict[str, str]:
    return json.loads((_KLASOR / f"{dil}.json").read_text(encoding="utf-8"))


def dil_sec(deger: str | None) -> str:
    return deger if deger in DILLER else VARSAYILAN_DIL


def konsol_dili() -> str:
    """Başlatıcı konsol dili: `AUTOCRIPT_KONSOL_DIL` (baslat.cmd belirler), yoksa sistem arayüz dili.

    Web arayüzünün varsayılanından (tr) bilerek farklıdır: Türkçe olmayan sistemde konsol
    İngilizce açılır. Ortam değişkeni `tr`/`en` dışında bir değerse `dil_sec` gibi tr'ye düşer
    (baslat.cmd değeri zaten normalleştirir).
    """
    ortam = os.environ.get("AUTOCRIPT_KONSOL_DIL")
    if ortam:
        return dil_sec(ortam)
    try:
        if sys.platform == "win32":
            import ctypes

            kod = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            return "tr" if kod == 0x1F else "en"
        ad = locale.getlocale()[0] or ""
        return "tr" if ad.lower().startswith(("tr", "turkish")) else "en"
    except Exception:
        return "en"


def _cerezden(baslik: str | None) -> str:
    if not baslik:
        return VARSAYILAN_DIL
    c = SimpleCookie()
    try:
        c.load(baslik)
    except Exception:
        return VARSAYILAN_DIL
    m = c.get(DIL_CEREZI)
    return dil_sec(m.value if m is not None else None)


def istek_dili(istek) -> str:
    """Starlette `Request` ya da ASGI `scope` alır; `dil` çerezini okur."""
    if isinstance(istek, dict):  # ASGI scope
        for ad, deger in istek.get("headers") or []:
            if ad.lower() == b"cookie":
                return _cerezden(deger.decode("latin-1"))
        return VARSAYILAN_DIL
    return _cerezden(istek.headers.get("cookie"))


class _Guvenli(dict):
    def __missing__(self, anahtar: str) -> str:
        return "{" + anahtar + "}"


def metin(anahtar: str, dil: str, **degisken: str) -> str:
    dil = dil_sec(dil)
    sablon = _katalog(dil).get(anahtar)
    if sablon is None:
        sablon = _katalog(VARSAYILAN_DIL).get(anahtar, anahtar)
    return sablon.format_map(_Guvenli(degisken)) if degisken else sablon


def _bicimler() -> str:
    from autocript.config import UPLOAD_EXTS

    return ", ".join(e.lstrip(".").upper() for e in UPLOAD_EXTS)


def hata_metni(
    kod: str, dil: str, params: dict | None = None, varyant: str | None = None
) -> str:
    tr = _katalog(VARSAYILAN_DIL)
    anahtar = f"hata.{kod}"
    if anahtar not in tr:
        anahtar = "hata.BEKLENMEYEN_HATA"
    elif varyant and f"{anahtar}.{varyant}" in tr:
        anahtar = f"{anahtar}.{varyant}"
    degisken = {**_VARSAYILAN_DEGISKEN, **{k: str(v) for k, v in (params or {}).items()}}
    degisken["site"] = metin(f"site.{degisken['site']}", dil)
    degisken["bicimler"] = _bicimler()
    return metin(anahtar, dil, **degisken)


def uyari_metni(kod: str, dil: str) -> str:
    return metin(f"uyari.{kod}", dil)


def yerellestir_hata(err: dict, dil: str) -> dict:
    out = dict(err)
    out["message"] = hata_metni(err.get("code", ""), dil, err.get("params"), err.get("varyant"))
    return out


def katalog_ui(dil: str) -> dict[str, str]:
    return {k: v for k, v in _katalog(dil_sec(dil)).items() if k.startswith(("ui.", "site."))}
