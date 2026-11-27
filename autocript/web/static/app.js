"use strict";

const $ = (id) => document.getElementById(id);

/* Metin kataloğu: sunucu sayfaya <script id="metinler" type="application/json"> olarak gömer. */
let KATALOG = null;

function katalog() {
  if (KATALOG === null) {
    try {
      KATALOG = JSON.parse($("metinler").textContent);
    } catch (e) {
      KATALOG = {};
    }
  }
  return KATALOG;
}

/* t(anahtar, değişken): eksik anahtarda anahtarın kendisini döndürür. */
function t(anahtar, degisken) {
  const s = katalog()[anahtar];
  if (typeof s !== "string") return anahtar;
  if (!degisken) return s;
  return s.replace(/\{(\w+)\}/g, (m, k) => (Object.prototype.hasOwnProperty.call(degisken, k) ? String(degisken[k]) : m));
}

/* Dil düğmesi: çerezi yazar, sayfayı yeniden yükler. İş sürerken showScreen onu kapatır. */
const dilDugmesi = $("dil-dugmesi");
if (dilDugmesi) {
  dilDugmesi.addEventListener("click", () => {
    const hedef = dilDugmesi.dataset && dilDugmesi.dataset.hedef;
    if (hedef !== "tr" && hedef !== "en") return;
    document.cookie = "dil=" + hedef + "; Path=/; Max-Age=31536000; SameSite=Strict";
    location.reload();
  });
}

const AŞAMALAR = [
  ["kaynak", "ui.adim_dosya_okunuyor"],
  ["ses", "ui.adim_ses_hazirlaniyor"],
  ["transkript", "ui.adim_metne_dokuluyor"],
  ["son", "ui.adim_son"],
];
const KONUŞMASIZ_ETİKET = { music: "ui.etiket_music", silence: "ui.etiket_silence", unknown: "ui.etiket_unknown" };
const SEG_COLORS = ["#8A5CD6", "#B05BC8", "#D85A9E", "#E8697F", "#F07A8A"];
const IG_CODE = /^(?=[A-Za-z0-9_-]*[A-Za-z0-9])[A-Za-z0-9_-]{5,}$/;
const YT_ID = /^[A-Za-z0-9_-]{11}$/;
const RETRY_CODES = new Set(["KAYNAK_GECICI", "SUNUCU_YENIDEN_BASLADI"]);

let autoSubmit = false;
let clickFromErrorBox = false;
let timer = null;
let jobFromLink = false;
let lastSubmittedLink = "";
let lastRetryUrl = "";
let lastPlainLines = [];

function clear(el) {
  while (el && el.firstChild) el.removeChild(el.firstChild);
}

function reducedMotion() {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/* Sekme arka plandayken CSS animasyonlarını durdur */
if (document.documentElement && typeof document.addEventListener === "function") {
  const syncVis = () => {
    if (document.documentElement.classList && document.documentElement.classList.toggle) {
      document.documentElement.classList.toggle("is-hidden", !!document.hidden);
    }
  };
  document.addEventListener("visibilitychange", syncVis);
  syncVis();
}

function mmss(sec, pad) {
  const t = Math.floor(sec);
  const m = Math.floor(t / 60);
  const s = String(t % 60).padStart(2, "0");
  return (pad ? String(m).padStart(2, "0") : String(m)) + ":" + s;
}

function stamp(t) {
  // Python formats.stamp ile aynı: saniye yüzdeliğe yuvarlanır, [dd:ss.ss]
  let cs = Math.round(Math.max(t, 0) * 100);
  const m = Math.floor(cs / 6000);
  cs -= m * 6000;
  const s = Math.floor(cs / 100);
  cs -= s * 100;
  return "[" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0") + "." + String(cs).padStart(2, "0") + "]";
}

function numFmt(n) {
  try {
    return Number(n).toLocaleString(t("ui.yerel_ayar"));
  } catch (e) {
    return String(n);
  }
}

function dateFmt(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(t("ui.yerel_ayar"), { day: "numeric", month: "long", year: "numeric" });
  } catch (e) {
    return iso;
  }
}

function keyLinkEl() {
  const a = document.createElement("a");
  a.href = "/kurulum";
  a.textContent = t("ui.anahtarlar");
  return a;
}

function showScreen(id) {
  // İş sürerken dil değişirse sayfa yenilenir ve işin ekrandaki takibi kopar: düğme kapalı kalır.
  const dilBtn = $("dil-dugmesi");
  if (dilBtn) dilBtn.disabled = id === "s-isl";
  ["s-ana", "s-isl", "sonuc", "hata"].forEach((sid) => {
    const el = $(sid);
    if (!el) return;
    const active = sid === id;
    el.hidden = !active;
    if (active && el.classList && el.classList.add && !reducedMotion()) {
      el.classList.remove("is-entering");
      el.classList.add("is-entering");
    }
  });
  if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
    window.scrollTo(0, 0);
  }
}

/* İstemci tarafı link ipucu (İL §8): parse_link ile uyumlu, gönderimi ASLA engellemez. */
function validateLink(raw) {
  const v = (raw || "").trim();
  if (!v) return { state: "", msg: t("ui.link_ipucu") };
  let u = null;
  try {
    u = new URL(v.includes("://") ? v : "https://" + v);
  } catch (e) {
    u = null;
  }
  if (!u || (u.protocol !== "http:" && u.protocol !== "https:")) {
    return { state: "bad", msg: t("ui.link_benzemiyor") };
  }
  if (u.username || u.password || (u.port && u.port !== "80" && u.port !== "443")) {
    return { state: "bad", msg: t("ui.link_gecersiz") };
  }
  const host = u.hostname.toLowerCase().replace(/^(www\.|m\.)/, "");
  const segs = u.pathname.split("/").filter(Boolean);
  if (host === "instagram.com") {
    const s = segs.length === 3 ? segs.slice(1) : segs;
    if (s.length === 2 && IG_CODE.test(s[1])) {
      if (s[0] === "reel" || s[0] === "reels") {
        return { state: "ok", msg: t("ui.link_ig_reel") };
      }
      if (s[0] === "p") {
        return { state: "ok", msg: t("ui.link_ig_gonderi") };
      }
    }
    return { state: "bad", msg: t("ui.link_desteklenmiyor") };
  }
  if (host === "youtu.be" || host === "youtube.com") {
    let id = "";
    if (host === "youtu.be") {
      id = segs[0] || "";
    } else if (segs.length === 2 && segs[0] === "shorts") {
      id = segs[1];
    } else if (segs.length === 1 && segs[0] === "watch") {
      id = u.searchParams.get("v") || "";
    }
    if (YT_ID.test(id)) return { state: "ok", msg: t("ui.link_yt") };
    return { state: "bad", msg: t("ui.link_desteklenmiyor") };
  }
  return { state: "bad", msg: t("ui.link_taninmadi") };
}

/* Gönderilen linkin sitesi: sıra bandı ve adım metni için. Boş ya da tanınmayan: Instagram. */
function siteOf(raw) {
  try {
    const v = (raw || "").trim();
    const u = new URL(v.includes("://") ? v : "https://" + v);
    const host = u.hostname.toLowerCase().replace(/^(www\.|m\.)/, "");
    return host === "youtu.be" || host === "youtube.com" ? "youtube" : "instagram";
  } catch (e) {
    return "instagram";
  }
}

function runCheck() {
  const linkEl = $("link");
  const checkEl = $("url-check");
  if (!linkEl || !checkEl) return { state: "", msg: t("ui.link_ipucu") };
  const r = validateLink(linkEl.value);
  if (checkEl.dataset) checkEl.dataset.state = r.state;
  checkEl.textContent = r.msg;
  if (typeof linkEl.setAttribute === "function") {
    linkEl.setAttribute("aria-invalid", r.state === "bad" ? "true" : "false");
  }
  return r;
}

function showError(message, keyLink, uploadFallback, opts) {
  const info = opts || {};
  const m = $("hata-mesaj");
  clear(m);
  m.textContent = message;
  if (keyLink) m.append(" ", keyLinkEl());

  const linkRow = $("hata-link");
  const errUrl = info.url || (jobFromLink ? lastSubmittedLink : "");
  if (linkRow) {
    if (errUrl) {
      linkRow.textContent = t("ui.denenen_baglanti", { url: errUrl });
      linkRow.hidden = false;
    } else {
      linkRow.textContent = "";
      linkRow.hidden = true;
    }
  }

  $("hata-yukle").hidden = uploadFallback === false;

  const dene = $("hata-dene");
  const canRetry = !!(RETRY_CODES.has(info.code) && errUrl);
  lastRetryUrl = canRetry ? errUrl : "";
  if (dene) dene.hidden = !canRetry;

  showScreen("hata");
  $("asama").hidden = true;
  $("sira").hidden = true;
}

function stageLabel(key, label) {
  return key === "kaynak" && jobFromLink ? t("ui.adim_video_iniyor") : t(label);
}

function setStep(idx, state, statusText) {
  const li = $("step-" + idx);
  const st = $("step-" + idx + "-status");
  if (li && li.dataset) li.dataset.state = state;
  if (st) st.textContent = statusText;
}

function updateVisualSteps(stage) {
  const s1Name = $("step-1-name");
  const s1Detail = $("step-1-detail");
  const s3Detail = $("step-3-detail");
  if (s1Name) s1Name.textContent = jobFromLink ? t("ui.adim_video_iniyor") : t("ui.adim_dosya_okunuyor");
  if (s1Detail) {
    s1Detail.textContent = jobFromLink
      ? (lastSubmittedLink || t("ui.adim_link_detay", { site: t("site." + siteOf(lastSubmittedLink)) }))
      : t("ui.adim_dosya_detay");
  }
  if (s3Detail) {
    s3Detail.textContent = stage === "son" ? t("ui.adim_son_detay") : t("ui.adim_yazi_detay");
  }

  // Adımlar yalnızca durum gösterir: Sırada, Sürüyor, Tamam (yüzde yok, İL §8).
  if (stage === null || stage === undefined || stage === "sira") {
    setStep(1, "waiting", t("ui.durum_sirada"));
    setStep(2, "waiting", t("ui.durum_sirada"));
    setStep(3, "waiting", t("ui.durum_sirada"));
    return;
  }
  const activeStep = stage === "kaynak" ? 1 : stage === "ses" ? 2 : 3;
  for (let i = 1; i <= 3; i++) {
    if (i < activeStep) setStep(i, "done", t("ui.durum_tamam"));
    else if (i === activeStep) setStep(i, "active", t("ui.durum_suruyor"));
    else setStep(i, "waiting", t("ui.durum_sirada"));
  }
}

function showStage(stage) {
  const box = $("asama");
  clear(box);
  // "sira" AŞAMALAR'a girmez; yalnızca bu aşamada 1. adımın üstünde ayrı satır olarak görünür.
  $("sira").hidden = stage !== "sira";
  if (stage === "sira") $("sira").textContent = t("ui.sira_bekleniyor", { site: t("site." + siteOf(lastSubmittedLink)) });
  updateVisualSteps(stage);

  if (stage === null || stage === undefined) {
    box.textContent = t("ui.sirada_bekliyor");
    box.hidden = false;
    return;
  }
  const idx = AŞAMALAR.findIndex((a) => a[0] === stage);
  AŞAMALAR.forEach(([key, label], i) => {
    const span = document.createElement("span");
    span.className = i === idx ? "aktif" : i < idx ? "bitti" : "bekliyor";
    span.textContent = (i === idx ? "● " : "") + stageLabel(key, label) + (i === idx ? "…" : "");
    box.appendChild(span);
    if (i < AŞAMALAR.length - 1) box.appendChild(document.createTextNode(" ▸ "));
  });
  box.hidden = false;
}

const MAX_TXT_LINE = 200;

// Python tarafıyla (segments.KISALTMALAR) aynı liste; test_kisaltma_listeleri_esit eşitliği denetler.
const KISALTMALAR = ["mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "vs.", "e.g.", "i.e.", "u.s.", "u.k."];

function isAbbreviation(text) {
  return KISALTMALAR.includes(text.replace(/^["'“”‘’()]+|["'“”‘’()]+$/g, "").toLowerCase());
}

function isSentenceEnd(text) {
  return !isAbbreviation(text) && /[.?!…]["'”’)]*$/.test(text);
}

function isLongBreak(text) {
  return !isAbbreviation(text) && /[.?!…:"”]["'”’)]*$/.test(text);
}

function splitLongSentence(tokens) {
  const out = [];
  let rem = tokens;
  while (rem.length > 0) {
    let total = 0;
    for (let i = 0; i < rem.length; i++) total += rem[i].text.length + (i > 0 ? 1 : 0);
    if (total <= MAX_TXT_LINE) {
      out.push(rem);
      break;
    }
    let bestBefore = -1;
    let firstAfter = -1;
    let acc = 0;
    for (let i = 0; i < rem.length - 1; i++) {
      acc += rem[i].text.length + (i > 0 ? 1 : 0);
      if (isLongBreak(rem[i].text)) {
        if (acc <= MAX_TXT_LINE) bestBefore = i;
        else if (firstAfter === -1) {
          firstAfter = i;
          break;
        }
      }
    }
    const cut = bestBefore !== -1 ? bestBefore : firstAfter;
    if (cut === -1) {
      out.push(rem);
      break;
    }
    out.push(rem.slice(0, cut + 1));
    rem = rem.slice(cut + 1);
  }
  return out;
}

function segTokens(doc, seg) {
  const words = doc.words || [];
  const range = seg.word_range || [0, 0];
  if (doc.timing === "word" && range[0] >= 0 && range[1] > range[0] && range[1] <= words.length) {
    const out = [];
    for (let i = range[0]; i < range[1]; i++) {
      const w = words[i];
      out.push({ text: w.text, start: w.start != null ? w.start : seg.start, word: w });
    }
    return out;
  }
  return (seg.text || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((text) => ({ text, start: seg.start, word: null }));
}

let tipCounter = 0;

function renderTokens(parent, tokens, unsureList) {
  tokens.forEach((tok, i) => {
    if (i > 0) parent.appendChild(document.createTextNode(" "));
    const w = tok.word;
    if (w && w.low_confidence) {
      const tipId = "tip-" + (tipCounter++);
      const span = document.createElement("span");
      span.className = "unsure";
      span.tabIndex = 0;
      const confText =
        w.confidence === null || w.confidence === undefined
          ? t("ui.guven_konusmasiz")
          : t("ui.guven", {
              yuzde: Math.round(w.confidence * 100),
              oran: w.confidence.toFixed(2).replace(".", t("ui.ondalik")),
            });
      span.title = confText;
      if (typeof span.setAttribute === "function") span.setAttribute("aria-describedby", tipId);
      span.textContent = tok.text;

      const tip = document.createElement("span");
      tip.className = "tip";
      tip.id = tipId;
      if (typeof tip.setAttribute === "function") tip.setAttribute("role", "tooltip");
      const b = document.createElement("b");
      b.textContent = confText;
      tip.appendChild(b);
      span.appendChild(tip);

      if (typeof span.addEventListener === "function") {
        span.addEventListener("keydown", (e) => {
          if (e.key === "Escape" && span.classList) span.classList.add("tip-off");
        });
        span.addEventListener("blur", () => { if (span.classList) span.classList.remove("tip-off"); });
        span.addEventListener("mouseleave", () => { if (span.classList) span.classList.remove("tip-off"); });
      }
      parent.appendChild(span);
      unsureList.push(span);
    } else {
      parent.appendChild(document.createTextNode(tok.text));
    }
  });
}

function renderLines(doc) {
  const events = [];
  (doc.segments || []).forEach((seg) => events.push({ start: seg.start, order: 0, seg }));
  (doc.non_speech || []).forEach((ns) => events.push({ start: ns.start, order: 1, ns }));
  events.sort((a, b) => a.start - b.start || a.order - b.order);

  const items = [];
  const unsureList = [];
  let buf = [];

  function pushLine(start, plainText, contentFn) {
    const li = document.createElement("li");
    li.className = "line";
    li.id = "line-" + items.length;
    const head = document.createElement("span");
    head.className = "ts";
    head.textContent = stamp(start);
    const body = document.createElement("p");
    body.className = "said";
    contentFn(body);
    li.appendChild(head);
    li.appendChild(body);
    items.push({ el: li, start, text: plainText });
  }

  function flush() {
    if (buf.length === 0) return;
    splitLongSentence(buf).forEach((chunk) => {
      const txt = chunk.map((t) => t.text).join(" ");
      pushLine(chunk[0].start, txt, (p) => renderTokens(p, chunk, unsureList));
    });
    buf = [];
  }

  events.forEach((ev) => {
    if (ev.ns) {
      flush();
      const label = "[" + t(KONUŞMASIZ_ETİKET[ev.ns.kind] || KONUŞMASIZ_ETİKET.unknown) + "]";
      pushLine(ev.start, label, (p) => {
        const el = document.createElement("span");
        el.className = "aralik";
        el.textContent = label;
        p.appendChild(el);
      });
      return;
    }
    segTokens(doc, ev.seg).forEach((tok) => {
      buf.push(tok);
      if (isSentenceEnd(tok.text)) flush();
    });
  });
  flush();
  return { items, unsureList };
}

// Kısaltılmış başlığın "devamını göster" düğmesi. Düğme yalnızca metin gerçekten 3 satırı aşınca görünür.
function baslikDugmesi(acik) {
  const btn = $("baslik-devam");
  if (!btn) return;
  btn.dataset.acik = acik ? "1" : "";
  if (typeof btn.setAttribute === "function") btn.setAttribute("aria-expanded", acik ? "true" : "false");
  btn.textContent = t(acik ? "ui.baslik_daha_az" : "ui.baslik_devami");
}

function baslikTasmasi() {
  const el = $("baslik");
  const btn = $("baslik-devam");
  if (!el || !btn) return;
  if (btn.dataset.acik) return;
  if (el.className !== "kisa") {
    btn.hidden = true;
    return;
  }
  btn.hidden = !(el.scrollHeight > el.clientHeight + 1);
}

(function baslikDugmesiniBagla() {
  const btn = $("baslik-devam");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const el = $("baslik");
    const acik = Boolean(btn.dataset.acik);
    el.className = acik ? "kisa" : "kisa acik";
    baslikDugmesi(!acik);
  });
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("resize", baslikTasmasi);
  }
})();

function renderMeta(doc) {
  const src = doc.source || {};
  const sourceEl = $("source");
  if (sourceEl) {
    clear(sourceEl);
    const platform = src.kind === "instagram"
      ? t("ui.platform_ig")
      : src.kind === "youtube"
        ? t("ui.platform_yt")
        : t("ui.platform_dosya");
    if (src.author) {
      const strong = document.createElement("strong");
      strong.textContent = src.author;
      sourceEl.appendChild(strong);
      sourceEl.appendChild(document.createTextNode(", " + platform));
    } else {
      sourceEl.textContent = platform;
    }
    sourceEl.hidden = false;
  }

  const baslikEl = $("baslik");
  baslikEl.textContent = src.title || t("ui.sonuc_hazir");
  // Instagram'da başlık gönderi açıklamasının tamamıdır: 3 satırla sınırlanır (YouTube etkilenmez).
  baslikEl.className = src.kind === "instagram" && src.title ? "kisa" : "";
  baslikDugmesi(false);

  const metaEl = $("meta");
  if (!metaEl) return;
  clear(metaEl);
  const stats = src.stats || {};
  const entries = [
    [t("ui.meta_hesap"), src.author],
    [t("ui.meta_tarih"), dateFmt(src.published_at)],
    [t("ui.meta_sure"), src.duration_s != null ? mmss(src.duration_s) : null],
    [t("ui.meta_izlenme"), stats.views != null ? numFmt(stats.views) : null],
    [t("ui.meta_begeni"), stats.likes != null ? numFmt(stats.likes) : null],
    [t("ui.meta_yorum"), stats.comments != null ? numFmt(stats.comments) : null],
  ].filter(([, v]) => v !== null && v !== undefined && v !== "");

  entries.forEach(([k, v]) => {
    const div = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    div.appendChild(dt);
    div.appendChild(dd);
    metaEl.appendChild(div);
  });
  metaEl.hidden = entries.length === 0;
}

function renderTrack(items, durationS) {
  const wrap = $("track-wrap");
  const track = $("track");
  const scaleEnd = $("scale-end");
  if (!wrap || !track) return;
  clear(track);
  if (items.length === 0) {
    wrap.hidden = true;
    return;
  }
  const total = Math.max(durationS || 0, items[items.length - 1].start + 1);
  if (scaleEnd) scaleEnd.textContent = mmss(total);

  function highlight(idx, scroll) {
    items.forEach((it, j) => {
      if (it.el.classList && it.el.classList.toggle) it.el.classList.toggle("is-current", j === idx);
    });
    const btns = track.children || [];
    for (let j = 0; j < btns.length; j++) {
      if (typeof btns[j].setAttribute === "function") {
        btns[j].setAttribute("aria-current", j === idx ? "true" : "false");
      }
    }
    if (scroll && typeof items[idx].el.scrollIntoView === "function") {
      items[idx].el.scrollIntoView({ block: "center", behavior: reducedMotion() ? "auto" : "smooth" });
    }
  }

  items.forEach((it, i) => {
    const nextStart = i < items.length - 1 ? items[i + 1].start : total;
    const dur = Math.max(0.5, nextStart - it.start);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "seg";
    if (btn.style) {
      btn.style.flex = String(dur);
      if (typeof btn.style.setProperty === "function") {
        const ci = Math.round((i * (SEG_COLORS.length - 1)) / Math.max(1, items.length - 1));
        btn.style.setProperty("--c", SEG_COLORS[ci]);
      }
    }
    if (typeof btn.setAttribute === "function") {
      btn.setAttribute(
        "aria-label",
        t("ui.satir_etiket", { n: i + 1, damga: stamp(it.start), metin: it.text.slice(0, 40) }),
      );
    }
    if (typeof btn.addEventListener === "function") {
      btn.addEventListener("click", () => highlight(i, true));
    }
    track.appendChild(btn);
  });
  wrap.hidden = false;
}

function renderResult(doc, jobId) {
  const warn = $("uyarilar");
  clear(warn);
  const uyarilar = doc.warnings || [];
  const keyRejected = uyarilar.some((w) => w.code === "ANAHTAR_REDDEDILDI");
  uyarilar.forEach((w) => {
    // Anahtar reddi uyarısı yedek motoru zaten söylüyor; ikinci uyarı gösterilmez.
    if (keyRejected && w.code === "YEDEK_MOTOR") return;
    const p = document.createElement("div");
    p.className = "uyari";
    p.textContent = w.message;
    if (w.code === "ANAHTAR_REDDEDILDI") p.append(" ", keyLinkEl());
    warn.appendChild(p);
  });

  renderMeta(doc);

  const box = $("satirlar");
  clear(box);
  const { items, unsureList } = renderLines(doc);
  lastPlainLines = items.map((it) => stamp(it.start) + " " + it.text);

  if (items.length === 0) {
    const empty = document.createElement("li");
    empty.className = "line";
    const p = document.createElement("p");
    p.className = "said";
    p.textContent = t("ui.konusma_yok");
    empty.appendChild(p);
    box.appendChild(empty);
  } else {
    items.forEach((it) => box.appendChild(it.el));
  }

  renderTrack(items, doc.source ? doc.source.duration_s : null);

  const tipBox = $("tip-box");
  const unsureCount = $("unsure-count");
  if (tipBox) {
    tipBox.hidden = unsureList.length === 0;
    if (unsureCount) {
      unsureCount.textContent =
        unsureList.length === 1 ? t("ui.kelime_tek") : t("ui.kelime_cok", { n: unsureList.length });
    }
    const firstBtn = $("first-unsure");
    if (firstBtn) {
      firstBtn.onclick = () => {
        const el = unsureList[0];
        if (!el) return;
        if (typeof el.scrollIntoView === "function") {
          el.scrollIntoView({ block: "center", behavior: reducedMotion() ? "auto" : "smooth" });
        }
        if (typeof el.focus === "function") el.focus({ preventScroll: true });
      };
    }
  }

  ["txt", "srt", "json"].forEach((ext) => {
    const a = $("dl-" + ext);
    if (!a) return;
    a.href = "/api/jobs/" + jobId + "/transcript." + ext;
    a.download = "transkript-" + jobId + "." + ext;
  });
  const toast = $("toast");
  if (toast) toast.textContent = "";

  showScreen("sonuc");
  baslikTasmasi(); // ölçüm ekran görünür olduktan sonra
  $("asama").hidden = true;
  $("sira").hidden = true;
}

async function poll(jobId) {
  try {
    const r = await fetch("/api/jobs/" + jobId);
    if (!r.ok) throw new Error("durum");
    const st = await r.json();
    if (st.state === "hata") {
      showError(
        (st.error && st.error.message) || t("ui.hata_genel"),
        !!(st.error && st.error.code === "ANAHTAR_REDDEDILDI"),
        st.error ? st.error.upload_fallback : undefined,
        st.error || {},
      );
      $("dok").disabled = false;
      return;
    }
    if (st.state === "bitti") {
      const t = await fetch("/api/jobs/" + jobId + "/transcript.json");
      if (!t.ok) throw new Error("transkript");
      renderResult(await t.json(), jobId);
      $("dok").disabled = false;
      return;
    }
    showStage(st.state === "sirada" ? null : st.stage);
  } catch (e) {
    showError(t("ui.ag_hatasi"));
    $("dok").disabled = false;
    return;
  }
  timer = setTimeout(() => poll(jobId), 1000);
}

async function submit(overrideLink) {
  clearTimeout(timer);
  const formErr = $("form-error");
  if (formErr) formErr.textContent = "";

  const link = overrideLink !== undefined ? overrideLink.trim() : $("link").value.trim();
  const file = overrideLink !== undefined ? null : $("dosya").files[0];
  if (!link && !file) {
    if (formErr) formErr.textContent = t("ui.baglanti_yok");
    else showError(t("ui.baglanti_yok"));
    return;
  }
  if (!link) {
    const maxMb = Number(document.body.dataset.maxUploadMb) || 500;
    if (file.size > maxMb * 1024 * 1024) {
      showError(t("ui.dosya_buyuk", { mb: maxMb }));
      return;
    }
  }
  $("dok").disabled = true;
  jobFromLink = !!link;
  lastSubmittedLink = link;
  showScreen("s-isl");
  showStage("kaynak");

  let init;
  if (link) {
    init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: link }) };
  } else {
    const fd = new FormData();
    fd.append("file", file);
    init = { method: "POST", body: fd };
  }
  try {
    const r = await fetch("/api/jobs", init);
    const body = await r.json();
    if (!r.ok) {
      showError(
        body.message || (link ? t("ui.link_gonderilemedi") : t("ui.yukleme_basarisiz")),
        body.code === "KURULUM_GEREKLI",
        body.upload_fallback,
        { code: body.code, url: link || "" },
      );
      $("dok").disabled = false;
      return;
    }
    poll(body.job_id);
  } catch (e) {
    showError(
      link ? t("ui.link_ag_hatasi") : t("ui.yukleme_ag_hatasi"),
      false,
      true,
      { url: link || "" },
    );
    $("dok").disabled = false;
  }
}

function updateDropLabel() {
  const f = $("dosya").files[0];
  const dropFile = $("drop-file");
  if (dropFile) dropFile.textContent = f ? t("ui.dosya_secildi", { ad: f.name }) : "";
}

function resetToHome() {
  clearTimeout(timer);
  lastSubmittedLink = "";
  lastRetryUrl = "";
  $("link").value = "";
  $("dosya").value = "";
  updateDropLabel();
  runCheck();
  const formErr = $("form-error");
  if (formErr) formErr.textContent = "";
  $("dok").disabled = false;
  showScreen("s-ana");
}

/* Desteklenen biçim metnini okunur biçime çevir (kaynak: sunucunun accept özniteliği) */
(function formatAcceptText() {
  const dosya = $("dosya");
  const sub = $("drop-sub");
  if (dosya && dosya.accept && sub) {
    const liste = dosya.accept
      .split(",")
      .map((s) => s.trim().replace(/^\./, "").toUpperCase())
      .filter(Boolean)
      .join(", ");
    if (liste) sub.textContent = t("ui.birak_alt") + " " + liste;
  }
})();

/* Üst çubuktaki "Kurulum hazır" göstergesini GET /api/kurulum'dan besle */
(async function syncSetupState() {
  const badge = $("setup-state");
  if (!badge || typeof fetch !== "function") return;
  try {
    const r = await fetch("/api/kurulum");
    if (!r.ok) return;
    const d = await r.json();
    const ok = !!(d && d.elevenlabs && d.elevenlabs.set);
    if (badge.dataset) badge.dataset.ok = ok ? "true" : "false";
    badge.textContent = ok ? t("ui.kurulum_hazir") : t("ui.anahtar_eksik");
    if (typeof badge.setAttribute === "function") {
      badge.setAttribute("aria-label", ok ? t("ui.kurulum_hazir_aria") : t("ui.anahtar_eksik_aria"));
    }
  } catch (e) {
    // sessiz geç
  }
})();

$("form").addEventListener("submit", (e) => {
  e.preventDefault();
  autoSubmit = false;
  submit();
});

$("hata-yukle").addEventListener("click", () => {
  autoSubmit = true;
  clickFromErrorBox = true;
  $("link").value = "";
  $("dosya").value = "";
  updateDropLabel();
  runCheck();
  $("dosya").click();
});

if ($("hata-dene")) {
  $("hata-dene").addEventListener("click", () => {
    if (!lastRetryUrl) return;
    $("link").value = lastRetryUrl;
    runCheck();
    submit(lastRetryUrl);
  });
}

if ($("hata-yeni")) $("hata-yeni").addEventListener("click", resetToHome);
if ($("new-run")) $("new-run").addEventListener("click", resetToHome);
if ($("home")) {
  $("home").addEventListener("click", (e) => {
    e.preventDefault();
    resetToHome();
  });
}

$("link").addEventListener("input", () => {
  if ($("link").value !== "") {
    $("dosya").value = "";
    updateDropLabel();
  }
  const formErr = $("form-error");
  if (formErr) formErr.textContent = "";
  runCheck();
});

if ($("paste")) {
  $("paste").addEventListener("click", async () => {
    const checkEl = $("url-check");
    try {
      const text = await navigator.clipboard.readText();
      if (!text.trim()) {
        if (checkEl) {
          if (checkEl.dataset) checkEl.dataset.state = "bad";
          checkEl.textContent = t("ui.pano_bos");
        }
        return;
      }
      $("link").value = text.trim();
      $("dosya").value = "";
      updateDropLabel();
      runCheck();
      if (typeof $("link").focus === "function") $("link").focus();
    } catch (e) {
      if (checkEl) {
        if (checkEl.dataset) checkEl.dataset.state = "bad";
        checkEl.textContent = t("ui.pano_izin");
      }
    }
  });
}

const dropEl = $("drop");
if (dropEl) {
  ["dragenter", "dragover"].forEach((ev) => {
    dropEl.addEventListener(ev, (e) => {
      e.preventDefault();
      if (dropEl.classList) dropEl.classList.add("is-over");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    dropEl.addEventListener(ev, () => {
      if (dropEl.classList) dropEl.classList.remove("is-over");
    });
  });
  dropEl.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
      $("dosya").files = e.dataTransfer.files;
      $("link").value = "";
      runCheck();
      updateDropLabel();
    }
  });
}

$("dosya").addEventListener("change", () => {
  if ($("dosya").files.length) {
    $("link").value = "";
    runCheck();
  }
  updateDropLabel();
  const go = autoSubmit && $("dosya").files.length;
  autoSubmit = false;
  if (go) submit();
});

$("dosya").addEventListener("cancel", () => {
  autoSubmit = false;
});

$("dosya").addEventListener("click", () => {
  if (!clickFromErrorBox) autoSubmit = false;
  clickFromErrorBox = false;
});

if ($("copy")) {
  $("copy").addEventListener("click", async () => {
    const toast = $("toast");
    try {
      await navigator.clipboard.writeText(lastPlainLines.join("\n") + "\n");
      if (toast) toast.textContent = t("ui.kopyalandi");
    } catch (e) {
      if (toast) toast.textContent = t("ui.kopyalanamadi");
    }
  });
}
