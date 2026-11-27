"use strict";

const $ = (id) => document.getElementById(id);
const SAĞLAYICILAR = ["elevenlabs", "groq"];

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

/* Dil düğmesi: çerezi yazar, sayfayı yeniden yükler. */
const dilDugmesi = $("dil-dugmesi");
if (dilDugmesi) {
  dilDugmesi.addEventListener("click", () => {
    const hedef = dilDugmesi.dataset && dilDugmesi.dataset.hedef;
    if (hedef !== "tr" && hedef !== "en") return;
    document.cookie = "dil=" + hedef + "; Path=/; Max-Age=31536000; SameSite=Strict";
    location.reload();
  });
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

function mesajYaz(id, metin, durum) {
  const el = $(id);
  if (!el) return;
  el.textContent = metin;
  const sinif = durum === "ok" ? "ok" : durum === "wait" ? "wait" : "bad";
  el.className = "status " + sinif;
  el.hidden = false;
}

function mesajGizle(id) {
  const el = $(id);
  if (!el) return;
  el.textContent = "";
  el.hidden = true;
}

function durumGoster(durum) {
  for (const p of SAĞLAYICILAR) {
    const d = durum[p] || { set: false, masked: null };
    const rozet = $("rozet-" + p);
    const kutu = $("kutu-" + p);
    const kayit = $("kayit-" + p);
    const meta = $("meta-" + p);
    const etiket = $("etiket-" + p);

    if (rozet) rozet.hidden = !d.set;
    if (kutu && kutu.classList) kutu.classList.toggle("is-empty", !d.set);
    if (kayit) kayit.textContent = d.set ? t("ui.kayitli_deger", { maske: d.masked }) : t("ui.kayitli_degil");
    if (meta) {
      meta.textContent = d.set
        ? t("ui.meta_dolu")
        : p === "elevenlabs"
          ? t("ui.el_meta_bos")
          : t("ui.groq_meta_bos");
    }
    if (etiket) etiket.textContent = d.set ? t("ui.yeni_anahtar_yapistir") : t("ui.anahtari_yapistir");
  }

  const groqVar = !!(durum.groq && durum.groq.set);
  const elVar = !!(durum.elevenlabs && durum.elevenlabs.set);

  if ($("kaldir-groq")) $("kaldir-groq").hidden = !groqVar;

  const badge = $("setup-state");
  if (badge) {
    if (badge.dataset) badge.dataset.ok = elVar ? "true" : "false";
    badge.textContent = elVar ? t("ui.kurulum_hazir") : t("ui.anahtar_eksik");
    if (typeof badge.setAttribute === "function") {
      badge.setAttribute("aria-label", elVar ? t("ui.kurulum_hazir_aria") : t("ui.anahtar_eksik_aria"));
    }
  }

  const devam = $("devam");
  if (devam) {
    if (elVar) {
      devam.classList.remove("devre-disi");
      devam.removeAttribute("aria-disabled");
    } else {
      devam.classList.add("devre-disi");
      devam.setAttribute("aria-disabled", "true");
    }
  }
}

async function json(yanit) {
  try {
    return await yanit.json();
  } catch (e) {
    return {};
  }
}

async function yukle() {
  try {
    const r = await fetch("/api/kurulum");
    if (!r.ok) throw new Error();
    durumGoster(await r.json());
  } catch (e) {
    mesajYaz("mesaj-genel", t("ui.kur_okunamadi"), "bad");
  }
}

async function kaydet(govde, mesajId, basariMetni) {
  mesajGizle("mesaj-genel");
  if (mesajId) mesajGizle(mesajId);
  try {
    const r = await fetch("/api/kurulum", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(govde),
    });
    const j = await json(r);
    if (!r.ok) {
      mesajYaz(mesajId || "mesaj-genel", j.message || t("ui.kaydedilemedi"), "bad");
      return false;
    }
    for (const p of Object.keys(govde)) {
      if ($("alan-" + p)) $("alan-" + p).value = "";
    }
    durumGoster(j);
    mesajYaz(mesajId || "mesaj-genel", basariMetni || t("ui.anahtar_kaydedildi"), "ok");
    return true;
  } catch (e) {
    mesajYaz(mesajId || "mesaj-genel", t("ui.kaydedilemedi_calisiyor"), "bad");
    return false;
  }
}

async function testEt(p) {
  const mid = "mesaj-" + p;
  mesajYaz(mid, t("ui.deneniyor"), "wait");
  const govde = { provider: p };
  const deger = $("alan-" + p).value;
  if (deger.trim() !== "") govde.key = deger;
  try {
    const r = await fetch("/api/kurulum/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(govde),
    });
    const j = await json(r);
    mesajYaz(mid, j.message || t("ui.test_yapilamadi"), r.ok && j.ok === true ? "ok" : "bad");
  } catch (e) {
    mesajYaz(mid, t("ui.test_yapilamadi_calisiyor"), "bad");
  }
}

for (const p of SAĞLAYICILAR) {
  const testBtn = $("test-" + p);
  const alan = $("alan-" + p);
  const form = $("form-" + p);
  if (testBtn) testBtn.addEventListener("click", () => testEt(p));
  if (alan) alan.addEventListener("input", () => mesajGizle("mesaj-" + p));
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = alan.value;
      if (v.trim() === "") {
        mesajYaz("mesaj-" + p, t("ui.bos_anahtar"), "bad");
        if (typeof alan.focus === "function") alan.focus();
        return;
      }
      kaydet({ [p]: v }, "mesaj-" + p, t("ui.anahtar_kaydedildi"));
    });
  }
}

if ($("kaldir-groq")) {
  $("kaldir-groq").addEventListener("click", () => {
    kaydet({ groq: "" }, "mesaj-groq", t("ui.groq_kaldirildi"));
  });
}

if ($("devam")) {
  $("devam").addEventListener("click", (e) => {
    if ($("devam").classList && $("devam").classList.contains("devre-disi")) e.preventDefault();
  });
}

yukle();
