"""Tur B yeni arayüz kontrolleri (İL §8, Task B1)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autocript.config import UPLOAD_EXTS
from autocript.metinler import katalog_ui
from tests.web.test_api import build

STATIC = Path(__file__).resolve().parents[2] / "autocript" / "web" / "static"


def _sayfalar(tmp_path) -> tuple[str, str]:
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        ana = client.get("/").text
        kurulum = client.get("/kurulum").text
    return ana, kurulum


def test_yeni_sayfa_yasakli_metinler(tmp_path):
    ana, kurulum = _sayfalar(tmp_path)
    for html in (ana, kurulum):
        for yasak in ("Videoyu sakla", "Önizleme", "Gemini", "İptal et"):
            assert yasak not in html, f"{yasak!r} sayfada olmamalı"


def test_yeni_sayfa_yardim_metni(tmp_path):
    ana, _ = _sayfalar(tmp_path)
    m = re.search(r'<[^>]*id="url-check"[^>]*>(.*?)</[^>]+>', ana, flags=re.S)
    assert m is not None, 'id="url-check" bulunamadı'
    assert m.group(1).strip() == "YouTube Shorts · Instagram Reels"


def test_yeni_sayfa_bicimler(tmp_path):
    ana, _ = _sayfalar(tmp_path)
    beklenen = ",".join(UPLOAD_EXTS)
    m_acc = re.search(r'id="dosya"[^>]*accept="([^"]*)"', ana)
    assert m_acc is not None and m_acc.group(1) == beklenen
    m_sub = re.search(r'id="drop-sub"[^>]*>(.*?)</span>', ana, flags=re.S)
    assert m_sub is not None, 'id="drop-sub" bulunamadı'
    gorunen = re.sub(r"<[^>]+>", "", m_sub.group(1))
    assert "MP4, MOV, MP3 veya M4A" not in ana
    for ext in UPLOAD_EXTS:
        assert ext.lstrip(".").upper() in gorunen.upper(), f"{ext} görünen biçim metninde yok"


def test_hareket_azaltma_css():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    m = re.search(r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{(.*)\}", css, flags=re.S)
    assert m is not None, "prefers-reduced-motion bloğu yok"
    blok = m.group(1)
    m_mesh = re.search(r"\.mesh\s+span\s*\{([^}]*)\}", blok, flags=re.S)
    assert m_mesh is not None, "prefers-reduced-motion içinde .mesh span kuralı yok"
    kural = m_mesh.group(1)
    assert re.search(r"animation\s*:\s*none", kural)
    assert re.search(r"transform\s*:\s*none", kural)


def test_ust_menu_opak(tmp_path):
    ana, kurulum = _sayfalar(tmp_path)
    for html in (ana, kurulum):
        m_hdr = re.search(r'<header[^>]*class="([^"]*)"', html)
        assert m_hdr is not None
        siniflar = m_hdr.group(1).split()
        assert "top" in siniflar and "glass" not in siniflar
    css = re.sub(r"/\*.*?\*/", "", (STATIC / "style.css").read_text(encoding="utf-8"), flags=re.S)
    m_top = re.search(r"(?:^|\})\s*\.top\s*\{([^}]*)\}", css, flags=re.S)
    assert m_top is not None, ".top kuralı yok"
    kural = m_top.group(1)
    m_bg = re.search(r"background(?:-color)?\s*:\s*([^;]+);", kural)
    assert m_bg is not None, ".top arka planı tanımlı değil"
    bg = m_bg.group(1).strip()
    assert "--glass" not in bg
    m_rgba = re.search(r"rgba\([^,]+,[^,]+,[^,]+,\s*([0-9.]+)\s*\)", bg)
    if m_rgba:
        assert float(m_rgba.group(1)) >= 1.0
    else:
        assert re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|rgb\([^)]+\)", bg), f"opak değil: {bg}"


def test_alan_kimlikleri(tmp_path):
    ana, _ = _sayfalar(tmp_path)
    assert 'id="link"' in ana
    assert 'id="dosya"' in ana
    assert 'id="url"' not in ana
    assert 'id="file"' not in ana


def test_giris_metni_iki_site(tmp_path):
    ana, _ = _sayfalar(tmp_path)
    m_lede = re.search(r'class="lede"[^>]*>(.*?)</p>', ana, flags=re.S)
    assert m_lede is not None
    assert "YouTube" in m_lede.group(1) and "Instagram" in m_lede.group(1)


def test_dis_kaynak_yok(tmp_path):
    ana, kurulum = _sayfalar(tmp_path)
    for html in (ana, kurulum):
        for attr in re.findall(r'<(?:script|link)\b[^>]*\b(?:src|href)="([^"]+)"', html, flags=re.I):
            assert not re.match(r"^(?:https?:)?//", attr), f"dış kaynak yasak: {attr}"


# ---------------------------------------------------------------- KT2 Task 6: EN/TR arayüz

_TR_HARF = re.compile("[çğıöşüÇĞİÖŞÜ]")
_GOMULU = re.compile(r'<script id="metinler" type="application/json">(.*?)</script>', re.S)
_DUGME = re.compile(r'<button id="dil-dugmesi".*?</button>', re.S)


def _sayfa(tmp_path, ad: str, dil: str | None) -> str:
    app, store, s = build(tmp_path)
    basliklar = {"Cookie": f"dil={dil}"} if dil else {}
    with TestClient(app) as client:
        r = client.get("/" if ad == "index" else "/kurulum", headers=basliklar)
    assert r.status_code == 200
    return r.text


@pytest.mark.parametrize("ad", ["index", "kurulum"])
def test_sayfa_iki_dilde(tmp_path, ad):
    en = _sayfa(tmp_path, ad, "en")
    assert '<html lang="en">' in en
    assert "{{" not in en and "__DIL" not in en
    govde = _DUGME.sub("", _GOMULU.sub("", en))
    assert not _TR_HARF.search(govde), _TR_HARF.search(govde)
    tr = _sayfa(tmp_path, ad, "tr")
    assert '<html lang="tr">' in tr
    assert "{{" not in tr
    assert _sayfa(tmp_path, ad, None) == tr
    baslik = "Video Transkript" if ad == "index" else "Kurulum - Video Transkript"
    assert f"<title>{baslik}</title>" in tr
    assert f"<title>{baslik}</title>" not in en
    if ad == "index":
        assert "Videodaki konuşmayı yazıya dök" in tr


def test_ui_anahtarlari_esit():
    tr, en = katalog_ui("tr"), katalog_ui("en")
    tr_ui = {k for k in tr if k.startswith("ui.")}
    en_ui = {k for k in en if k.startswith("ui.")}
    assert tr_ui == en_ui and tr_ui
    kullanilan: set[str] = set()
    for ad in ("index.html", "kurulum.html"):
        kullanilan |= set(re.findall(r"\{\{(ui\.[a-z_.]+)\}\}", (STATIC / ad).read_text(encoding="utf-8")))
    for ad in ("app.js", "kurulum.js"):
        kullanilan |= set(re.findall(r'"(ui\.[a-z_.]+)"', (STATIC / ad).read_text(encoding="utf-8")))
    assert kullanilan - tr_ui == set(), "katalogda olmayan anahtar"
    assert tr_ui - kullanilan == set(), "kullanılmayan ui anahtarı"
    for k in tr_ui:
        assert tr[k].strip() and en[k].strip(), k
        assert sorted(re.findall(r"\{\w+\}", tr[k])) == sorted(re.findall(r"\{\w+\}", en[k])), k


def test_metinler_json_kacisli(tmp_path, monkeypatch):
    kotu = "</script><b>x</b>"
    gercek = katalog_ui

    def sahte(dil):
        d = dict(gercek(dil))
        d["ui.ana_baslik"] = kotu
        return d

    monkeypatch.setattr("autocript.web.app.katalog_ui", sahte)
    html = _sayfa(tmp_path, "index", "tr")
    m = _GOMULU.search(html)
    assert m is not None
    assert "\\u003c/script>" in m.group(1) and "<" not in m.group(1)
    assert json.loads(m.group(1))["ui.ana_baslik"] == kotu
    # Sayfa bozulmadı: yalnızca iki script etiketi (gömülü katalog + app.js), başlıkta kaçışlı metin.
    assert html.count("</script>") == 2
    assert "&lt;/script&gt;&lt;b&gt;x&lt;/b&gt;" in html


@pytest.mark.parametrize("ad", ["index", "kurulum"])
def test_dil_dugmesi_sayfada(tmp_path, ad):
    for dil, hedef, etiket in (("tr", "en", "English"), ("en", "tr", "Türkçe")):
        html = _sayfa(tmp_path, ad, dil)
        m = re.search(r'<button id="dil-dugmesi"([^>]*)>(.*?)</button>', html, re.S)
        assert m is not None
        assert 'class="dil"' in m.group(1) and f'data-hedef="{hedef}"' in m.group(1)
        assert f'lang="{hedef}"' in m.group(1)
        assert m.group(2).strip() == etiket
