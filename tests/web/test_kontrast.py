"""WCAG AA (>= 4,5:1) kontrast ölçümü: küçük metin renkleri en kötü zeminde (İL §8, Task B2)."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "autocript" / "web" / "static"


def _hex_rgb(kod: str) -> tuple[float, float, float]:
    h = kod.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgba(ifade: str) -> tuple[float, float, float, float]:
    ifade = ifade.strip()
    if ifade.startswith("#"):
        r, g, b = _hex_rgb(ifade)
        return (r, g, b, 1.0)
    m = re.fullmatch(
        r"rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?\s*\)",
        ifade,
    )
    assert m is not None, f"renk ayrıştırılamadı: {ifade!r}"
    return (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4) or 1.0))


def _birlestir(ust: tuple[float, float, float, float], alt: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b, a = ust
    return (
        r * a + alt[0] * (1.0 - a),
        g * a + alt[1] * (1.0 - a),
        b * a + alt[2] * (1.0 - a),
    )


def _parlaklik(rgb: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _kontrast(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    l1, l2 = sorted((_parlaklik(fg), _parlaklik(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _degiskenler(css: str) -> dict[str, str]:
    temiz = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    m = re.search(r":root\s*\{([^}]*)\}", temiz, flags=re.S)
    assert m is not None, ":root bloğu bulunamadı"
    return {
        k.strip(): v.strip()
        for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", m.group(1))
    }


def _kural(css: str, secici: str) -> dict[str, str]:
    """`secici { ... }` bloğunun bildirimleri (yorumsuz, @media dışı düz kural)."""
    temiz = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    m = re.search(r"(?:^|\})\s*" + re.escape(secici) + r"\s*\{([^}]*)\}", temiz, flags=re.S)
    assert m is not None, f"{secici} kuralı yok"
    return {k.strip(): v.strip() for k, v in re.findall(r"([a-z-]+)\s*:\s*([^;]+);", m.group(1))}


def _renk(deger: str, v: dict[str, str]) -> tuple[float, float, float]:
    m = re.fullmatch(r"var\((--[a-z0-9-]+)\)", deger.strip())
    return _hex_rgb(v[m.group(1)] if m else deger)


def test_dil_dugmesi_kontrasti():
    """Dil düğmesi (normal, hover, focus): metin/zemin >= 4,5:1. Yeni renk yok: değişkenler ve capsule zemini."""
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    v = _degiskenler(css)
    normal = _kural(css, ".dil")
    renk_n = _renk(normal["color"], v)
    zemin_n = _renk(normal["background"], v)
    durumlar = {"normal": (renk_n, zemin_n)}
    for ad, secici in (("hover", ".dil:hover"), ("focus", ".dil:focus-visible")):
        k = _kural(css, secici)
        durumlar[ad] = (
            _renk(k.get("color", normal["color"]), v),
            _renk(k.get("background", normal["background"]), v),
        )
    for ad, (fg, bg) in durumlar.items():
        oran = _kontrast(fg, bg)
        assert oran >= 4.5, f".dil {ad} kontrastı {oran:.2f}:1 (< 4.5:1)"
    # Üst bar opaktır (#FFFFFF); düğme zemini onun üstünde de okunur kalmalı.
    ust = _hex_rgb(_kural(css, ".top")["background"])
    assert _kontrast(renk_n, ust) >= 4.5


def _sinif_kumesi(html: str) -> set[str]:
    kume: set[str] = set()
    for degerler in re.findall(r'class="([^"]*)"', html):
        kume |= set(degerler.split())
    return kume


def test_kontrast_iki_dil(tmp_path):
    """tr ve en sayfaları aynı CSS sınıflarını kullanır: dil, ölçülmemiş bir renk çifti getirmez."""
    from fastapi.testclient import TestClient

    from tests.web.test_api import build

    app, store, s = build(tmp_path)
    with TestClient(app) as c:
        for yol in ("/", "/kurulum"):
            tr = c.get(yol, headers={"Cookie": "dil=tr"}).text
            en = c.get(yol, headers={"Cookie": "dil=en"}).text
            assert _sinif_kumesi(tr) == _sinif_kumesi(en), yol


def test_kucuk_yazi_kontrasti():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    v = _degiskenler(css)

    # En kötü zemin: --glass, en koyu leke #3A1A63'ün üstünde (İL §8, Task B2).
    en_koyu_leke = _hex_rgb("#3A1A63")
    cam_zemin = _birlestir(_rgba(v["--glass"]), en_koyu_leke)
    opak_panel = _birlestir(_rgba(v["--solid"]), en_koyu_leke)

    # Cam panel üstündeki küçük metin / ipucu / meta / durum renkleri
    for ad in ("--ink", "--ink-soft", "--ok", "--err", "--magenta-text"):
        fg = _hex_rgb(v[ad])
        oran = _kontrast(fg, cam_zemin)
        assert oran >= 4.5, f"{ad} cam zeminde {oran:.2f}:1 (< 4.5:1)"
        oran_opak = _kontrast(fg, opak_panel)
        assert oran_opak >= 4.5, f"{ad} solid zeminde {oran_opak:.2f}:1 (< 4.5:1)"

    # Rozet, uyarı, kayıt kutusu ve aktif kapsül düğmesi gibi özel zeminler
    ozel = [
        ("ok rozet", _hex_rgb(v["--ok"]), _hex_rgb(v["--ok-bg"])),
        ("err rozet", _hex_rgb(v["--err"]), _hex_rgb(v["--err-bg"])),
        ("sira/ipucu kutusu", _hex_rgb(v["--ink"]), _hex_rgb(v["--marker-soft"])),
        ("kayıt kutusu meta", _hex_rgb(v["--ink-soft"]), _hex_rgb("#F4EFF8")),
        ("aktif kapsül sol", _hex_rgb("#FFFFFF"), _hex_rgb(v["--plum"])),
        ("aktif kapsül sağ", _hex_rgb("#FFFFFF"), _hex_rgb(v["--magenta"])),
        ("birincil düğme", _hex_rgb(v["--ink"]), _hex_rgb("#FFB547")),
    ]
    for etiket, fg, bg in ozel:
        oran = _kontrast(fg, bg)
        assert oran >= 4.5, f"{etiket} kontrastı {oran:.2f}:1 (< 4.5:1)"


def test_devami_dugmesi_kontrasti():
    """'Devamını göster' düğmesi (normal ve hover) cam ve solid zeminde >= 4,5:1."""
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    v = _degiskenler(css)
    en_koyu_leke = _hex_rgb("#3A1A63")
    zeminler = {
        "cam": _birlestir(_rgba(v["--glass"]), en_koyu_leke),
        "solid": _birlestir(_rgba(v["--solid"]), en_koyu_leke),
    }
    normal = _kural(css, ".devami")
    assert normal["background"] == "none"
    hover = _kural(css, ".devami:hover")
    for durum, kural in (("normal", normal), ("hover", hover)):
        fg = _renk(kural["color"], v)
        for zad, bg in zeminler.items():
            oran = _kontrast(fg, bg)
            assert oran >= 4.5, f".devami {durum} {zad} zeminde {oran:.2f}:1 (< 4.5:1)"
