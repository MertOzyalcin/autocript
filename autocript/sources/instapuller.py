"""InstapullerSource: instapuller'ı alt süreç olarak çağırır (İL §6.4, KT2 Task 8).

Site (instagram ya da youtube) `parse_link(...).platform` değerinden gelir; her sitenin kendi
sırası ve durum dosyası vardır. YouTube için instapuller yalnızca ses indirir.

instapuller'ın kodu içe aktarılmaz; yalnızca JSON çıktılı komut satırı kullanılır.
Kullanıcıya gösterilen mesaj her zaman `hatalar` tablosundan gelir; instapuller'ın
`message`/`upload_fallback`/stderr değerleri yalnızca `detail` ve günlüğe gider.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from autocript.audio import probe
from autocript.config import Settings
from autocript.links.parse import parse_link
from autocript.sources.hatalar import INSTAPULLER_KODLARI, hata
from autocript.sources.site_sira import SiteSiralari
from autocript.types import JobRequest, SourceError, SourceMeta, SourceResult

log = logging.getLogger(__name__)

_STDERR_SON = 500


def _temiz_ortam(settings: Settings) -> dict[str, str]:
    """Mevcut ortam; INSTAPULLER_*/FFPROBE_BIN çıkarılır, yalnızca argümanlar geçerli olur."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith("INSTAPULLER_") and k.upper() != "FFPROBE_BIN"
    }
    env["PYTHONPATH"] = str(Path(settings.instapuller_src).resolve())
    env["PYTHONUTF8"] = "1"
    return env


def _detay(parcalar: list[str | None], stderr: str) -> str | None:
    son = stderr.strip()[-_STDERR_SON:]
    liste = [p for p in parcalar if p]
    if son:
        liste.append(f"stderr: {son}")
    return " | ".join(liste) or None


class InstapullerSource:
    def __init__(self, settings: Settings, siralar: SiteSiralari, *, run=subprocess.run):
        self.settings = settings
        self.siralar = siralar
        self._run = run

    def resolve(self, request: JobRequest, on_stage: Callable[[str], None]) -> SourceResult:
        s = self.settings
        # Yalnızca kanonik adres instapuller'a gider.
        parsed = parse_link(request.url or "")
        kanonik = parsed.canonical_url
        site = parsed.platform
        work_dir = Path(request.work_dir).resolve()
        # Eksik klasör yanlışlıkla IG_ARAC_YOK sayılmasın (cwd olarak kullanılıyor).
        work_dir.mkdir(parents=True, exist_ok=True)

        # JS ön kontrolü: ortam yoksa instapuller çağrılmaz, site sırası alınmaz (Argon 012).
        js_yol: str | None = None
        if site == "youtube":
            js_yol = str(Path(s.js_runtime_bin).resolve())
            if not Path(s.js_runtime_bin).is_file():
                raise hata("JS_ORTAMI_YOK", detail=f"JS çalışma ortamı bulunamadı: {js_yol}", site=site)

        bulunan = shutil.which(s.ffprobe_bin)
        if bulunan is None:
            raise hata("FFPROBE_YOK", detail=f"ffprobe bulunamadı: {s.ffprobe_bin}")
        ffprobe = str(Path(bulunan).resolve())

        args = [
            s.instapuller_python, "-m", "instapuller", "fetch",
            "--out-dir", str(work_dir),
            "--ffprobe-bin", ffprobe,
            "--state-file", str((Path(s.instapuller_state_dir) / f"instapuller-{site}.json").resolve()),
            "--max-duration", str(s.max_duration_s),
            "--max-size-mb", str(s.max_link_mb),
        ]
        if js_yol is not None:
            args += ["--js-runtime-bin", js_yol]
        args += ["--", kanonik]

        def cagri() -> SourceResult:
            on_stage("kaynak")  # yalnızca kilit alındıktan sonra, bir kez
            return self._cagir(args, work_dir, site)

        return self.siralar.sira(site).calistir(cagri, on_wait=lambda: on_stage("sira"))

    def _cagir(self, args: list[str], work_dir: Path, site: str) -> SourceResult:
        s = self.settings
        try:
            p = self._run(
                args,
                shell=False,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=s.link_timeout_s,
                cwd=work_dir,
                env=_temiz_ortam(s),
            )
        except subprocess.TimeoutExpired as e:
            raise hata("KAYNAK_GECICI", detail=f"instapuller {e.timeout} sn içinde bitmedi", site=site) from e
        except OSError as e:
            raise hata("IG_ARAC_YOK", detail=f"instapuller başlatılamadı: {e}", site=site) from e

        stdout = p.stdout or ""
        stderr = p.stderr or ""
        if stderr.strip():
            log.info("instapuller stderr:\n%s", stderr.strip())

        if p.returncode == 1 and not stdout.strip() and "No module named" in stderr:
            raise hata("IG_ARAC_YOK", detail=_detay([], stderr), site=site)
        if p.returncode not in (0, 1):
            raise hata("BEKLENMEYEN_HATA", detail=_detay([f"çıkış kodu {p.returncode}"], stderr), site=site)

        satirlar = stdout.strip().splitlines()
        try:
            veri = json.loads(satirlar[-1]) if satirlar else None
        except ValueError:
            veri = None
        if not isinstance(veri, dict) or "ok" not in veri:
            raise hata("BEKLENMEYEN_HATA", detail=_detay(["stdout geçerli JSON değil"], stderr), site=site)

        if veri.get("ok") is True:
            return self._basari(veri, work_dir, stderr, site)
        return self._hata(veri, stderr, site)

    def _hata(self, veri: dict, stderr: str, site: str) -> SourceResult:
        err = veri.get("error")
        err = err if isinstance(err, dict) else {}
        ip_kod = str(err.get("code") or "")
        kod = INSTAPULLER_KODLARI.get(ip_kod, "BEKLENMEYEN_HATA")
        if kod == "IG_ARAC_GUNCEL_DEGIL":
            log.warning("instapuller IG_ARAC_GUNCEL_DEGIL döndü: yt-dlp güncellenmeli")
        ayrinti = _detay([f"instapuller: {ip_kod}" if ip_kod else None, str(err["detail"]) if err.get("detail") else None], stderr)
        log.warning("instapuller hatası %s -> %s: %s", ip_kod, kod, ayrinti)
        raise hata(kod, detail=ayrinti, site=site)

    def _basari(self, veri: dict, work_dir: Path, stderr: str, site: str) -> SourceResult:
        s = self.settings
        ham = veri.get("video_path")
        meta_ham = veri.get("meta")
        if not isinstance(ham, str) or not ham or not isinstance(meta_ham, dict):
            raise hata("BEKLENMEYEN_HATA", detail="başarı yanıtında video_path/meta eksik", site=site)
        video = Path(ham).resolve()
        if not video.is_relative_to(work_dir.resolve()) or not video.is_file():
            raise hata("BEKLENMEYEN_HATA", detail=f"video_path iş klasöründe değil: {ham}", site=site)
        if meta_ham.get("kind") != site:
            raise hata("BEKLENMEYEN_HATA", detail=f"beklenmeyen meta.kind: {meta_ham.get('kind')!r}", site=site)

        try:
            info = probe(video)
        except SourceError as e:
            raise hata("DOSYA_BOZUK", detail=e.detail, site=site) from e
        if not info.has_audio:
            raise hata("DOSYA_SES_YOK", site=site)
        if info.duration_s > s.max_duration_s:
            raise hata("VIDEO_UZUN", detail=f"süre {info.duration_s:.1f} sn", site=site)

        stats_ham = meta_ham.get("stats") if isinstance(meta_ham.get("stats"), dict) else {}
        stats = {k: stats_ham.get(k) for k in ("views", "likes", "comments")}
        sure_ham = meta_ham.get("duration_s")
        sure = (
            round(float(sure_ham), 2)
            if isinstance(sure_ham, (int, float)) and not isinstance(sure_ham, bool)
            else round(info.duration_s, 2)
        )
        meta = SourceMeta(
            kind=site,  # type: ignore[arg-type]
            url=meta_ham.get("url"),
            platform_id=meta_ham.get("platform_id"),
            title=meta_ham.get("title"),
            author=meta_ham.get("author"),
            published_at=meta_ham.get("published_at"),
            duration_s=sure,
            stats=stats,
        )
        return SourceResult(meta=meta, audio_path=video, transcript=None)
