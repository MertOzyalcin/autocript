"""app.js davranışı: gerçek dosya Node altında, testin içindeki küçük sahte DOM ile çalışır."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autocript.metinler import katalog_ui
from tests.web.test_api import build

STATIC = Path(__file__).resolve().parents[2] / "autocript" / "web" / "static"
NODE = shutil.which("node")

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const els = {};
function makeEl(id) {
  const el = {
    id, hidden: false, textContent: "", disabled: false, className: "", title: "", href: "", download: "",
    dataset: {}, children: [], listeners: {}, _value: "", files: [],
    classList: { add() {}, remove() {} },
    addEventListener(t, f) { (el.listeners[t] = el.listeners[t] || []).push(f); },
    dispatch(t) { const ev = { preventDefault() {} }; (el.listeners[t] || []).forEach((f) => f(ev)); },
    click() { el.clicked = true; (el.listeners.click || []).forEach((f) => f({})); },
    appendChild(c) { el.children.push(c); return c; },
    append(...a) { a.forEach((c) => el.children.push(c)); },
    removeChild(c) { el.children.splice(el.children.indexOf(c), 1); },
    get firstChild() { return el.children[0] || null; },
  };
  Object.defineProperty(el, "value", {
    get() { return el._value; },
    set(v) { el._value = v; if (v === "") el.files = []; },
  });
  return el;
}
global.document = {
  body: makeEl("body"),
  getElementById(id) { return (els[id] = els[id] || makeEl(id)); },
  createElement(tag) { return makeEl(tag); },
  createTextNode(t) { return { text: t }; },
};
els.metinler = makeEl("metinler");
els.metinler.textContent = %KATALOG%;
global.location = { reloaded: 0, reload() { this.reloaded += 1; } };
const calls = [];
global.FormData = class { constructor() { this.parts = []; } append(k, v) { this.parts.push([k, v]); } };
global.fetch = (url, init) => {
  calls.push({ url, init });
  if (init && init.method === "POST") {
    return Promise.resolve({ ok: true, status: 202, json: async () => ({ job_id: "j1" }) });
  }
  return new Promise(() => {});
};
global.setTimeout = () => 0;
global.clearTimeout = () => {};
const src = fs.readFileSync(process.argv[1], "utf8") + "\n;globalThis.__app = { AŞAMALAR, showStage, showScreen, renderResult, t, validateLink: typeof validateLink === 'function' ? validateLink : null };";
vm.runInThisContext(src);
(async () => {
const tick = () => new Promise((r) => setImmediate(r));
const $ = (id) => document.getElementById(id);
const file = { name: "a.mp4", size: 10 };
function pickFile() { $("dosya").files = [file]; $("dosya")._value = "C:\fakepath\a.mp4"; $("dosya").dispatch("change"); }
const out = {};
%BODY%
  console.log(JSON.stringify(out));
})();
"""


def _katalog_js(dil: str) -> str:
    """Sunucunun sayfaya gömdüğü kataloğun aynısı (JS dizgesi olarak)."""
    return json.dumps(json.dumps(katalog_ui(dil), ensure_ascii=False), ensure_ascii=False)


def calistir(govde: str, dil: str = "tr") -> dict:
    if NODE is None:
        pytest.skip("node yok")
    kod = HARNESS.replace("%KATALOG%", _katalog_js(dil)).replace("%BODY%", govde)
    r = subprocess.run(
        [NODE, "-e", kod, str(STATIC / "app.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_sayfa_link_alani_ve_uyari(tmp_path):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text
    assert 'id="link"' in html and 'id="dosya"' in html
    # type="url" tarayıcıda protokolsüz (instagram.com/...) ve geçersiz linkleri 422'ye gitmeden keser.
    assert 'type="url"' not in html
    assert "YouTube Shorts · Instagram Reels" in html
    assert (
        "YouTube ve Instagram linkleri resmi bir yol kullanmaz ve sitelerin kullanım şartlarıyla çelişebilir. "
        "Hiçbir hesap ya da şifre kullanılmaz. Yalnızca kullanım hakkına sahip olduğunuz içerikleri kullanın."
    ) in html


def test_hata_yukle_linki_temizler():
    out = calistir(r"""
      $("link").value = "https://www.instagram.com/reel/ABCDE12/";
      $("hata-yukle").dispatch("click");
      pickFile();
      await tick(); await tick();
      const posts = calls.filter((c) => c.init && c.init.method === "POST");
      out.n = posts.length;
      out.multipart = posts[0].init.body instanceof FormData;
      out.json_header = !!(posts[0].init.headers && posts[0].init.headers["Content-Type"]);
      out.link = $("link").value;
    """)
    assert out["n"] == 1
    assert out["multipart"] is True
    assert out["json_header"] is False
    assert out["link"] == ""


def test_link_yazinca_dosya_temizlenir():
    out = calistir(r"""
      pickFile();
      $("link").value = "https://www.instagram.com/reel/ABCDE12/";
      $("link").dispatch("input");
      out.dosya = $("dosya").value;
      out.dosyalar = $("dosya").files.length;
    """)
    assert out["dosya"] == "" and out["dosyalar"] == 0


def test_link_yolu_json_gonderir():
    out = calistir(r"""
      $("link").value = " https://www.instagram.com/reel/ABCDE12/ ";
      $("form").dispatch("submit");
      await tick(); await tick();
      const posts = calls.filter((c) => c.init && c.init.method === "POST");
      out.n = posts.length;
      out.init = posts[0].init;
      out.etiket = $("asama").children[0].textContent;
    """)
    assert out["n"] == 1
    assert out["init"]["headers"] == {"Content-Type": "application/json"}
    assert json.loads(out["init"]["body"]) == {"url": "https://www.instagram.com/reel/ABCDE12/"}
    assert out["etiket"] == "● Video indiriliyor…"


def test_yukleme_etiketi_dosya_okunuyor():
    out = calistir(r"""
      pickFile();
      $("form").dispatch("submit");
      await tick();
      out.etiket = $("asama").children[0].textContent;
    """)
    assert out["etiket"] == "● Dosya okunuyor…"


def test_sira_asamasi_ayri_satir():
    out = calistir(r"""
      const once = JSON.stringify(__app.AŞAMALAR);
      __app.showStage("sira");
      out.degismedi = once === JSON.stringify(__app.AŞAMALAR);
      out.sira_gorunur = $("sira").hidden === false;
      out.sira_metin = $("sira").textContent;
      __app.showStage("kaynak");
      out.sira_sonra = $("sira").hidden;
    """)
    assert out["degismedi"] is True
    assert out["sira_gorunur"] is True
    assert out["sira_metin"] == "Instagram için sıra bekleniyor"
    assert out["sira_sonra"] is True


def test_validate_link_youtube():
    out = calistir(r"""
      out.shorts = __app.validateLink("https://www.youtube.com/shorts/abcdefghijk");
      out.be = __app.validateLink("youtu.be/abcdefghijk?si=x");
      out.watch = __app.validateLink("https://m.youtube.com/watch?v=abcdefghijk&t=1");
      out.kisa = __app.validateLink("https://youtube.com/watch?v=kisa");
      out.kanal = __app.validateLink("https://youtube.com/@kanal");
      $("link").value = "https://www.youtube.com/shorts/abcdefghijk";
      $("form").dispatch("submit");
      await tick(); await tick();
      __app.showStage("sira");
      out.sira_yt = $("sira").textContent;
      out.adim_yt = $("step-1-detail").textContent;
    """)
    for k in ("shorts", "be", "watch"):
        assert out[k]["state"] == "ok", k
        assert out[k]["msg"] == "YouTube linki tanındı."
    assert out["kisa"]["state"] == "bad" and out["kanal"]["state"] == "bad"
    assert out["sira_yt"] == "YouTube için sıra bekleniyor"
    assert "youtube.com" in out["adim_yt"]

    en = calistir(r"""
      $("link").value = "https://youtu.be/abcdefghijk";
      $("form").dispatch("submit");
      await tick(); await tick();
      __app.showStage("sira");
      out.sira = $("sira").textContent;
      $("link").value = "https://www.instagram.com/reel/ABCDE12/";
      $("form").dispatch("submit");
      await tick(); await tick();
      __app.showStage("sira");
      out.sira_ig = $("sira").textContent;
    """, dil="en")
    assert en["sira"] == "Waiting in the YouTube queue"
    assert en["sira_ig"] == "Waiting in the Instagram queue"


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_sonuc_kaynak_youtube(dil):
    out = calistir(r"""
      __app.renderResult({
        source: { kind: "youtube", author: "Kanal", title: "T", duration_s: 12.5, stats: { views: 5, likes: 1, comments: 0 } },
        timing: "word",
        words: [{ text: "Merhaba.", start: 0.2, end: 0.5, confidence: 0.95, low_confidence: false }],
        segments: [{ start: 0.2, end: 0.5, text: "Merhaba.", word_range: [0, 1] }],
        non_speech: [],
        warnings: [],
      }, "j_yt");
      const metin = (n) => (n.text !== undefined ? n.text : (n.children || []).map(metin).join(""));
      out.kaynak = metin($("source"));
      out.beklenen = __app.t("ui.platform_yt");
      out.dosya = __app.t("ui.platform_dosya");
    """, dil=dil)
    assert out["beklenen"] == "YouTube Shorts"
    assert out["beklenen"] in out["kaynak"]
    assert out["dosya"] not in out["kaynak"]


def test_422_hata_kutusu_ve_upload_fallback_false():
    out = calistir(r"""
      global.fetch = () => Promise.resolve({ ok: false, status: 422,
        json: async () => ({ code: "LINK_GECERSIZ", message: "Bu link olmaz.", upload_fallback: false }) });
      $("link").value = "https://example.com/x";
      $("form").dispatch("submit");
      await tick(); await tick();
      out.mesaj = $("hata-mesaj").textContent;
      out.hata_gorunur = $("hata").hidden === false;
      out.yukle_gizli = $("hata-yukle").hidden;
      global.fetch = () => Promise.resolve({ ok: false, status: 422,
        json: async () => ({ code: "IG_ERISILEMEDI", message: "Erişilemedi.", upload_fallback: true }) });
      $("form").dispatch("submit");
      await tick(); await tick();
      out.yukle_gizli2 = $("hata-yukle").hidden;
    """)
    assert out["mesaj"] == "Bu link olmaz."
    assert out["hata_gorunur"] is True
    assert out["yukle_gizli"] is True
    assert out["yukle_gizli2"] is False


def test_istemci_link_denetimi():
    out = calistir(r"""
      if (!__app.validateLink) throw new Error("validateLink yok");
      out.hesapli = __app.validateLink("instagram.com/kullanici/reel/ABCDE12/");
      out.tv = __app.validateLink("https://www.instagram.com/tv/ABCDE12/");
      out.yt = __app.validateLink("https://youtube.com/shorts/abcdefghijk");
      $("link").value = "https://www.instagram.com/tv/ABCDE12/";
      $("form").dispatch("submit");
      await tick(); await tick();
      out.post_sayisi = calls.filter((c) => c.init && c.init.method === "POST").length;
    """)
    assert out["hesapli"]["state"] == "ok"
    assert out["tv"]["state"] == "bad"
    assert out["yt"]["state"] == "ok" and out["yt"]["msg"] == "YouTube linki tanındı."
    assert out["post_sayisi"] == 1


def test_kurulum_kaydetmeden_test(tmp_path):
    app, store, s = build(tmp_path)
    with TestClient(app) as client:
        html = client.get("/kurulum").text
    assert "tarihinde kaydedildi" not in html
    if NODE is None:
        pytest.skip("node yok")
    kod = r"""
const fs = require("fs");
const vm = require("vm");
const els = {};
function makeEl(id) {
  const attrs = {};
  const cls = new Set();
  const el = {
    id, hidden: false, textContent: "", disabled: false, className: "", value: "", dataset: {},
    children: [], listeners: {},
    classList: {
      add(c) { cls.add(c); },
      remove(c) { cls.delete(c); },
      toggle(c, on) { if (on === undefined) { if (cls.has(c)) cls.delete(c); else cls.add(c); } else if (on) cls.add(c); else cls.delete(c); },
      contains(c) { return cls.has(c); },
    },
    setAttribute(k, v) { attrs[k] = String(v); },
    removeAttribute(k) { delete attrs[k]; },
    getAttribute(k) { return attrs[k] || null; },
    addEventListener(t, f) { (el.listeners[t] = el.listeners[t] || []).push(f); },
    dispatch(t) { const ev = { preventDefault() {} }; (el.listeners[t] || []).forEach((f) => f(ev)); },
    focus() {},
  };
  return el;
}
global.document = {
  documentElement: makeEl("html"),
  hidden: false,
  getElementById(id) { return (els[id] = els[id] || makeEl(id)); },
  addEventListener() {},
};
const calls = [];
global.fetch = (url, init) => {
  calls.push({ url, init });
  if (url === "/api/kurulum" && (!init || !init.method)) {
    return Promise.resolve({
      ok: true,
      json: async () => ({ elevenlabs: { set: false, masked: null }, groq: { set: false, masked: null } }),
    });
  }
  return Promise.resolve({ ok: true, json: async () => ({ ok: true, message: "Anahtar çalışıyor." }) });
};
els.metinler = makeEl("metinler");
els.metinler.textContent = %KATALOG%;
global.location = { reloaded: 0, reload() { this.reloaded += 1; } };
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
(async () => {
  const tick = () => new Promise((r) => setImmediate(r));
  await tick(); await tick();
  const $ = (id) => document.getElementById(id);
  const out = {};
%BODY%
  console.log(JSON.stringify(out));
})();
"""
    out = _kurulum_calistir(kod, r"""
      $("alan-elevenlabs").value = "sk_yeni_anahtar_12345";
      $("test-elevenlabs").dispatch("click");
      await tick(); await tick();
      const testCall = calls.find((c) => c.url === "/api/kurulum/test");
      out.body = testCall ? JSON.parse(testCall.init.body) : null;
    """)
    assert out["body"] == {"provider": "elevenlabs", "key": "sk_yeni_anahtar_12345"}

    # Aynı düzenek: kurulum sayfasında dil düğmesi ve metinler (Task 6).
    out = _kurulum_calistir(kod, r"""
      out.kayit_tr = $("kayit-elevenlabs").textContent;
      out.rozet = $("setup-state").textContent;
      $("dil-dugmesi").dataset.hedef = "en";
      $("dil-dugmesi").dispatch("click");
      out.cerez = document.cookie;
      out.yuklendi = location.reloaded;
    """)
    assert out["kayit_tr"] == "Kayıtlı değil" and out["rozet"] == "Anahtar eksik"
    assert out["cerez"] == "dil=en; Path=/; Max-Age=31536000; SameSite=Strict"
    assert out["yuklendi"] == 1
    out = _kurulum_calistir(kod, r"""
      out.kayit = $("kayit-elevenlabs").textContent;
      out.rozet = $("setup-state").textContent;
    """, dil="en")
    assert out["kayit"] == "Not saved" and out["rozet"] == "Key missing"


def _kurulum_calistir(kod: str, govde: str, dil: str = "tr") -> dict:
    kod = kod.replace("%KATALOG%", _katalog_js(dil)).replace("%BODY%", govde)
    r = subprocess.run(
        [NODE, "-e", kod, str(STATIC / "kurulum.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_yeniden_dene_yalnizca_gecici_hatada():
    out = calistir(r"""
      $("link").value = "https://www.instagram.com/reel/ABCDE12/";
      global.fetch = (url, init) => {
        if (init && init.method === "POST") return Promise.resolve({ ok: true, status: 202, json: async () => ({ job_id: "j1" }) });
        return Promise.resolve({ ok: true, json: async () => ({
          state: "hata", error: { code: "KAYNAK_GECICI", message: "Geçici.", upload_fallback: true, url: "https://www.instagram.com/reel/ABCDE12/" }
        }) });
      };
      $("form").dispatch("submit");
      await tick(); await tick(); await tick(); await tick();
      out.gecici_gizli = $("hata-dene").hidden;

      global.fetch = (url, init) => {
        if (init && init.method === "POST") return Promise.resolve({ ok: true, status: 202, json: async () => ({ job_id: "j2" }) });
        return Promise.resolve({ ok: true, json: async () => ({
          state: "hata", error: { code: "IG_RATE_LIMIT", message: "Sınır.", upload_fallback: true, url: "https://www.instagram.com/reel/ABCDE12/" }
        }) });
      };
      $("form").dispatch("submit");
      await tick(); await tick(); await tick(); await tick();
      out.sinir_gizli = $("hata-dene").hidden;
    """)
    assert out["gecici_gizli"] is False
    assert out["sinir_gizli"] is True


def test_sunucu_yeniden_basladi_link_gosterir_ve_sifirlanir():
    out = calistir(r"""
      $("link").value = "https://www.instagram.com/reel/ABCDE12/";
      global.fetch = (url, init) => {
        if (init && init.method === "POST") return Promise.resolve({ ok: true, status: 202, json: async () => ({ job_id: "j1" }) });
        return Promise.resolve({ ok: true, json: async () => ({
          state: "hata", error: { code: "SUNUCU_YENIDEN_BASLADI", message: "Sunucu yeniden başladı.", upload_fallback: true }
        }) });
      };
      $("form").dispatch("submit");
      await tick(); await tick(); await tick(); await tick();
      out.link_gizli = $("hata-link").hidden;
      out.link_metin = $("hata-link").textContent;
      out.dene_gizli = $("hata-dene").hidden;

      $("hata-yeni").dispatch("click");
      // Sıfırlama sonrası dosya yükleme hatasında eski link sızmamalı
      global.fetch = (url, init) => {
        if (init && init.method === "POST") return Promise.resolve({ ok: true, status: 202, json: async () => ({ job_id: "j2" }) });
        return Promise.resolve({ ok: true, json: async () => ({
          state: "hata", error: { code: "SUNUCU_YENIDEN_BASLADI", message: "Sunucu yeniden başladı.", upload_fallback: true }
        }) });
      };
      pickFile();
      $("form").dispatch("submit");
      await tick(); await tick(); await tick(); await tick();
      out.dosya_link_gizli = $("hata-link").hidden;
      out.dosya_dene_gizli = $("hata-dene").hidden;
    """)
    assert out["link_gizli"] is False
    assert "https://www.instagram.com/reel/ABCDE12/" in out["link_metin"]
    assert out["dene_gizli"] is False
    assert out["dosya_link_gizli"] is True
    assert out["dosya_dene_gizli"] is True


def test_gorsel_adimlar_ve_sonuc_ekrani():
    out = calistir(r"""
      __app.showStage("sira");
      out.sira_st1 = $("step-1").dataset.state;
      __app.showStage("kaynak");
      out.kaynak_st = [$("step-1").dataset.state, $("step-2").dataset.state, $("step-3").dataset.state];
      __app.showStage("ses");
      out.ses_st = [$("step-1").dataset.state, $("step-2").dataset.state, $("step-3").dataset.state];
      __app.showStage("son");
      out.son_st = [$("step-1").dataset.state, $("step-2").dataset.state, $("step-3").dataset.state];
      out.son_detay = $("step-3-detail").textContent;

      __app.renderResult({
        source: { kind: "instagram", author: "@deneme", title: "Başlık", duration_s: 12.5, stats: { likes: 42, comments: 3, views: null } },
        timing: "word",
        words: [
          { text: "Merhaba", start: 0.2, end: 0.5, confidence: 0.95, low_confidence: false },
          { text: "dünya.", start: 0.6, end: 1.0, confidence: 0.55, low_confidence: true },
        ],
        segments: [{ start: 0.2, end: 1.0, text: "Merhaba dünya.", word_range: [0, 2] }],
        non_speech: [],
        warnings: [],
      }, "j_test");
      out.baslik = $("baslik").textContent;
      out.meta_gizli = $("meta").hidden;
      out.meta_sayi = $("meta").children.length;
      out.track_sayi = $("track").children.length;
      out.tip_gizli = $("tip-box").hidden;
      out.unsure_metin = $("unsure-count").textContent;
      out.satir_sayi = $("satirlar").children.length;
      out.dl_txt = $("dl-txt").href;
    """)
    assert out["sira_st1"] == "waiting"
    assert out["kaynak_st"] == ["active", "waiting", "waiting"]
    assert out["ses_st"] == ["done", "active", "waiting"]
    assert out["son_st"] == ["done", "done", "active"]
    assert "Son düzenleme" in out["son_detay"]
    assert out["baslik"] == "Başlık"
    assert out["meta_gizli"] is False
    assert out["meta_sayi"] == 4  # Hesap, Süre, Beğeni, Yorum (views null -> yok)
    assert out["track_sayi"] == 1
    assert out["tip_gizli"] is False
    assert out["unsure_metin"] == "1 kelime"
    assert out["satir_sayi"] == 1
    assert out["dl_txt"] == "/api/jobs/j_test/transcript.txt"


def test_kurulum_form_kaydet():
    if NODE is None:
        pytest.skip("node yok")
    kod = r"""
const fs = require("fs");
const vm = require("vm");
const els = {};
function makeEl(id) {
  const attrs = {};
  const cls = new Set();
  return {
    id, hidden: false, textContent: "", disabled: false, className: "", value: "", dataset: {},
    children: [], listeners: {},
    classList: {
      add(c) { cls.add(c); },
      remove(c) { cls.delete(c); },
      toggle(c, on) { if (on) cls.add(c); else cls.delete(c); },
      contains(c) { return cls.has(c); },
    },
    setAttribute(k, v) { attrs[k] = String(v); },
    removeAttribute(k) { delete attrs[k]; },
    getAttribute(k) { return attrs[k] || null; },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    dispatch(t) { const ev = { preventDefault() {} }; (this.listeners[t] || []).forEach((f) => f(ev)); },
    focus() {},
  };
}
global.document = {
  documentElement: makeEl("html"),
  hidden: false,
  getElementById(id) { return (els[id] = els[id] || makeEl(id)); },
  addEventListener() {},
};
const calls = [];
global.fetch = (url, init) => {
  calls.push({ url, init });
  if (url === "/api/kurulum" && (!init || !init.method)) {
    return Promise.resolve({
      ok: true,
      json: async () => ({ elevenlabs: { set: false, masked: null }, groq: { set: false, masked: null } }),
    });
  }
  return Promise.resolve({
    ok: true,
    json: async () => ({ elevenlabs: { set: true, masked: "sk_…9999" }, groq: { set: false, masked: null } }),
  });
};
els.metinler = makeEl("metinler");
els.metinler.textContent = %KATALOG%;
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
(async () => {
  const tick = () => new Promise((r) => setImmediate(r));
  await tick(); await tick();
  const $ = (id) => document.getElementById(id);
  $("alan-elevenlabs").value = "sk_yeni_anahtar_9999";
  $("form-elevenlabs").dispatch("submit");
  await tick(); await tick();
  const putCall = calls.find((c) => c.init && c.init.method === "PUT");
  console.log(JSON.stringify({
    body: putCall ? JSON.parse(putCall.init.body) : null,
    alan: $("alan-elevenlabs").value,
    rozet: $("setup-state").textContent,
    devam_devre_disi: $("devam").classList.contains("devre-disi"),
  }));
})();
"""
    r = subprocess.run(
        [NODE, "-e", kod.replace("%KATALOG%", _katalog_js("tr")), str(STATIC / "kurulum.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["body"] == {"elevenlabs": "sk_yeni_anahtar_9999"}
    assert out["alan"] == ""
    assert out["rozet"] == "Kurulum hazır"
    assert out["devam_devre_disi"] is False


# --- Dil seçeneği (KT2 Task 6) ---


def test_dil_dugmesi_cerez_yazar():
    out = calistir(r"""
      $("dil-dugmesi").dataset.hedef = "en";
      $("dil-dugmesi").dispatch("click");
      out.cerez = document.cookie;
      out.yuklendi = location.reloaded;
      // Tanınmayan hedef çerez yazmaz
      document.cookie = "";
      $("dil-dugmesi").dataset.hedef = "xx";
      $("dil-dugmesi").dispatch("click");
      out.kotu_cerez = document.cookie;
      out.kotu_yuklendi = location.reloaded;
    """)
    assert out["cerez"] == "dil=en; Path=/; Max-Age=31536000; SameSite=Strict"
    assert out["yuklendi"] == 1
    assert out["kotu_cerez"] == "" and out["kotu_yuklendi"] == 1


def test_dil_dugmesi_is_surerken_kapali():
    out = calistir(r"""
      out.once = $("dil-dugmesi").disabled;
      $("link").value = "https://www.instagram.com/reel/ABCDE12/";
      $("form").dispatch("submit");
      await tick();
      out.surerken = $("dil-dugmesi").disabled;
      __app.showScreen("sonuc");
      out.sonuc = $("dil-dugmesi").disabled;
      __app.showScreen("s-isl");
      __app.showScreen("hata");
      out.hata = $("dil-dugmesi").disabled;
    """)
    assert out["once"] is False and out["surerken"] is True
    assert out["sonuc"] is False and out["hata"] is False


def test_ingilizce_arayuz_metinleri():
    out = calistir(r"""
      out.eksik = __app.t("ui.olmayan_anahtar");
      out.degisken = __app.t("ui.dosya_buyuk", { mb: 500 });
      out.yt = __app.validateLink("https://youtube.com/shorts/abcdefghijk");
      out.bos = __app.validateLink("");
      __app.showStage("sira");
      out.sira = $("sira").textContent;
      __app.showStage("kaynak");
      out.etiket = $("asama").children[0].textContent;
      __app.renderResult({
        source: { kind: "instagram", author: "@x", duration_s: 12.5, stats: { views: 1234567, likes: 3 } },
        timing: "word",
        words: [{ text: "Hello.", start: 0.2, end: 0.5, confidence: 0.55, low_confidence: true }],
        segments: [{ start: 0.2, end: 1.0, text: "Hello.", word_range: [0, 1] }],
        non_speech: [{ start: 2.0, end: 3.0, kind: "music" }],
        warnings: [],
      }, "j_en");
      out.baslik = $("baslik").textContent;
      out.meta = $("meta").children.map((d) => d.children[0].textContent + "=" + d.children[1].textContent);
      out.tip = $("unsure-count").textContent;
      out.ns = $("satirlar").children[1].children[1].children[0].textContent;
      out.kaynak = $("source").children.length;
    """, dil="en")
    assert out["eksik"] == "ui.olmayan_anahtar"
    assert out["degisken"] == "The file is over 500 MB."
    assert out["yt"]["state"] == "ok" and out["yt"]["msg"] == "YouTube link recognized."
    assert out["bos"]["msg"] == "YouTube Shorts · Instagram Reels"
    assert out["sira"] == "Waiting in the Instagram queue"
    assert out["etiket"] == "● Reading the file…"
    assert out["baslik"] == "Transcript ready"
    assert "Views=1,234,567" in out["meta"] and "Length=0:12" in out["meta"]
    assert out["tip"] == "1 word"
    assert out["ns"] == "[music]"


# --- İngilizce kısaltmalar (KT2 Task 4) ---

SATIR_OKU = r"""
      const metin = (n) => (n.text !== undefined ? n.text : (n.children || []).map(metin).join(""));
      out.satirlar = $("satirlar").children.map((li) => [li.children[0].textContent, metin(li.children[1])]);
"""


def _ekran_satirlari(doc: dict) -> list[list[str]]:
    govde = (
        "__app.renderResult(" + json.dumps(doc) + ', "j_en");' + SATIR_OKU
    )
    return calistir(govde)["satirlar"]


def _belge(words: list[dict], segments: list[dict]) -> dict:
    return {
        "source": {"kind": "upload", "duration_s": 10.0},
        "timing": "word", "words": words, "segments": segments,
        "non_speech": [], "warnings": [],
    }


def test_ingilizce_ekran():
    from tests.export.test_formats import _CUMLELER, _ingilizce_belge

    d = _ingilizce_belge()
    satirlar = _ekran_satirlari(_belge(d["words"], d["segments"]))
    assert [tuple(s) for s in satirlar] == _CUMLELER
    # Tek uzun segment içinde de aynı satırlar.
    tek = _ingilizce_belge(tek_segment=True)
    assert [tuple(s) for s in _ekran_satirlari(_belge(tek["words"], tek["segments"]))] == _CUMLELER


def test_kisaltma_tirnak_parantez():
    # 200 karakteri aşan cümle Mr. noktasından bölünmez.
    metin =["x" * 9] * 18 + ["Mr."] + ["y" * 9] * 5 + ["bitti."]
    words = [
        {"i": i, "text": t, "start": round(i * 0.1, 2), "end": round(i * 0.1 + 0.05, 2),
         "confidence": 0.9, "low_confidence": False}
        for i, t in enumerate(metin)
    ]
    seg = [{"start": 0.0, "end": words[-1]["end"], "text": " ".join(metin), "word_range": [0, len(words)]}]
    satirlar = _ekran_satirlari(_belge(words, seg))
    assert not any(s[1].endswith("Mr.") for s in satirlar)
    # Tırnak ve parantezli kısaltmalar cümleyi bitirmez.
    kelimeler = ["(e.g.", "tea", '"Dr.', "Smith", "left."]
    w2 = [
        {"i": i, "text": t, "start": round(i * 0.3, 2), "end": round(i * 0.3 + 0.25, 2),
         "confidence": 0.9, "low_confidence": False}
        for i, t in enumerate(kelimeler)
    ]
    s2 = [{"start": 0.0, "end": w2[-1]["end"], "text": " ".join(kelimeler), "word_range": [0, 5]}]
    assert [s[1] for s in _ekran_satirlari(_belge(w2, s2))] == ['(e.g. tea "Dr. Smith left.']


def test_kisaltma_listeleri_esit():
    import re

    from autocript.transcript.segments import KISALTMALAR

    kaynak = (STATIC / "app.js").read_text(encoding="utf-8")
    m = re.search(r"const KISALTMALAR = \[(.*?)\];", kaynak, re.S)
    assert m, "app.js içinde KISALTMALAR dizisi yok"
    assert set(re.findall(r'"([^"]+)"', m.group(1))) == set(KISALTMALAR)


_IG_DOC = r"""
  const doc = (kind, title) => ({
    source: { kind, author: "hesap", title, duration_s: 42 },
    timing: "word",
    words: [{ text: "Merhaba.", start: 0.2, end: 0.5, confidence: 0.95, low_confidence: false }],
    segments: [{ start: 0.2, end: 0.5, text: "Merhaba.", word_range: [0, 1] }],
    non_speech: [],
    warnings: [],
  });
"""


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_instagram_basligi_uc_satir_ve_devami(dil):
    """Uzun Instagram açıklaması 'kisa' sınıfıyla 3 satıra iner; düğme açar/kapar, metni dile göre."""
    out = calistir(_IG_DOC + r"""
      $("baslik").scrollHeight = 480; $("baslik").clientHeight = 116;  // 12 satır, 3'e kırpılmış
      __app.renderResult(doc("instagram", "uzun açıklama"), "j1");
      out.sinif = $("baslik").className;
      out.gizli = $("baslik-devam").hidden;
      out.metin = $("baslik-devam").textContent;
      $("baslik-devam").click();
      out.sinif_acik = $("baslik").className;
      out.metin_acik = $("baslik-devam").textContent;
      out.acik = $("baslik-devam").dataset.acik;
      $("baslik-devam").click();
      out.sinif_kapali = $("baslik").className;
      out.metin_kapali = $("baslik-devam").textContent;
      out.beklenen_ac = __app.t("ui.baslik_devami");
      out.beklenen_kapa = __app.t("ui.baslik_daha_az");
    """, dil=dil)
    assert out["sinif"] == "kisa"
    assert out["gizli"] is False
    assert out["metin"] == out["beklenen_ac"]
    assert out["sinif_acik"] == "kisa acik"
    assert out["metin_acik"] == out["beklenen_kapa"]
    assert out["acik"] == "1"
    assert out["sinif_kapali"] == "kisa"
    assert out["metin_kapali"] == out["beklenen_ac"]
    assert (out["beklenen_ac"], out["beklenen_kapa"]) == (
        ("Devamını göster", "Daha az göster") if dil == "tr" else ("Show more", "Show less")
    )


def test_kisa_instagram_basliginda_dugme_yok():
    out = calistir(_IG_DOC + r"""
      $("baslik").scrollHeight = 77; $("baslik").clientHeight = 77;
      __app.renderResult(doc("instagram", "kısa"), "j1");
      out.sinif = $("baslik").className;
      out.gizli = $("baslik-devam").hidden;
    """)
    assert out == {"sinif": "kisa", "gizli": True}


def test_youtube_basligi_sinirlanmaz():
    """Önce açılmış bir Instagram sonucu, sonra YouTube: sınıf ve düğme sıfırlanır."""
    out = calistir(_IG_DOC + r"""
      $("baslik").scrollHeight = 480; $("baslik").clientHeight = 116;
      __app.renderResult(doc("instagram", "uzun"), "j1");
      $("baslik-devam").click();
      __app.renderResult(doc("youtube", "YouTube başlığı"), "j2");
      out.sinif = $("baslik").className;
      out.gizli = $("baslik-devam").hidden;
      out.acik = $("baslik-devam").dataset.acik;
    """)
    assert out == {"sinif": "", "gizli": True, "acik": ""}


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_devami_dugmesi_sayfada(tmp_path, dil):
    """Gerçek <button>: klavyeyle odaklanır ve Enter/Boşluk ile çalışır; başlığı denetler."""
    app, store, s = build(tmp_path)
    with TestClient(app) as c:
        html = c.get("/", headers={"Cookie": f"dil={dil}"}).text
    metin = "Devamını göster" if dil == "tr" else "Show more"
    assert (
        f'<button type="button" class="devami" id="baslik-devam" aria-controls="baslik" '
        f'aria-expanded="false" hidden>{metin}</button>'
    ) in html
