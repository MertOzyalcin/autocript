"""Proje içi araçlar: ffmpeg ve instapuller'ı proje klasörü altına indirir (hash doğrulamalı)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from autocript import tls
from autocript.metinler import konsol_dili, metin

FFMPEG_SURUM = "btbn-n9.0.2-lgpl-shared"
FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-31-12-59/"
    "ffmpeg-n9.0.2-39-g7adfbe40dc-win64-lgpl-shared-9.0.zip"
)
# GitHub asset digest'i ve indirilen dosyanın hash'i aynıdır.
FFMPEG_SHA256 = "e907b01fa4783913151237e37df2a10fa97d99a1598a021bf59d4ae62ffed4c0"
FFMPEG_ZIP_KOK = "ffmpeg-n9.0.2-39-g7adfbe40dc-win64-lgpl-shared-9.0/"

_EXELER = ("ffmpeg.exe", "ffprobe.exe")
_DLLER = (
    "avcodec-63.dll", "avdevice-63.dll", "avfilter-12.dll", "avformat-63.dll",
    "avutil-61.dll", "swresample-7.dll", "swscale-10.dll",
)
_LISANS = "LICENSE.txt"

JS_URL = (
    "https://github.com/quickjs-ng/quickjs/releases/download/v0.18.0/"
    "qjs-windows-x86_64.exe"
)
JS_SHA256 = "ff03398d74ea6e6bd3a8e58058f7003225abcac229d7d57775b7aaae812a49c7"


def _hata(neden: str) -> str:
    dil = konsol_dili()
    return f"{metin('konsol.ffmpeg_hata', dil)}\n{metin('konsol.ayrinti', dil, neden=neden)}"


class AracHatasi(Exception):
    """Kullanıcıya olduğu gibi gösterilecek, konsol diline göre hazır mesajı taşır."""


def _sil(p: Path) -> None:
    try:
        p.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _ffmpeg_fazlalarini_sil(ffmpeg_klasoru: Path, tutulacak: tuple[Path, ...]) -> None:
    """tools/ffmpeg/ altında tutulacak liste dışındaki her dosya ve klasörü siler (eski kurulumlardan kalanlar)."""
    tut = {p.resolve() for p in tutulacak}
    ust = {p.parent.resolve() for p in tutulacak}
    for p in sorted(ffmpeg_klasoru.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        r = p.resolve()
        try:
            if p.is_dir() and not p.is_symlink():
                if r in ust:
                    continue
                shutil.rmtree(p, ignore_errors=True)
            elif r not in tut:
                p.unlink()
        except OSError:
            pass


def _indir(c: httpx.Client, url: str, part: Path) -> str:
    """url'yi part dosyasına akıtır, SHA-256 değerini döndürür."""
    h = hashlib.sha256()
    with c.stream("GET", url) as r:
        r.raise_for_status()
        with part.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                h.update(chunk)
                f.write(chunk)
    return h.hexdigest()


def _yeni_istemci() -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(30.0, read=60.0),
        verify=tls.ssl_context(),
    )


def _ffmpeg_tam_mi(ust: Path) -> bool:
    """kurulu.json eşleşiyor, iki exe ve yedi dll yerinde mi."""
    try:
        d = json.loads((ust / "kurulu.json").read_text(encoding="utf-8"))
        if d.get("surum") != FFMPEG_SURUM or d.get("sha256") != FFMPEG_SHA256:
            return False
    except (OSError, ValueError, AttributeError):
        return False
    return all((ust / "bin" / n).is_file() for n in (*_EXELER, *_DLLER))


def ensure_ffmpeg(
    root: Path, *, client: httpx.Client | None = None, say=print
) -> tuple[Path, Path]:
    ust = root / "tools" / "ffmpeg"
    bin_dir = ust / "bin"
    ffmpeg, ffprobe = (bin_dir / n for n in _EXELER)
    tutulacak = (
        ffmpeg, ffprobe, *(bin_dir / n for n in _DLLER), ust / _LISANS, ust / "kurulu.json"
    )
    if _ffmpeg_tam_mi(ust):
        _ffmpeg_fazlalarini_sil(ust, tutulacak)
        return ffmpeg, ffprobe

    eski_var = ffmpeg.is_file() and ffprobe.is_file()
    say(metin("konsol.ffmpeg_indiriliyor", konsol_dili()))
    tools = root / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    part = tools / "ffmpeg-indirme.part"
    acilis = ust / "_acilis"
    own_client = client is None
    c = client or _yeni_istemci()
    try:
        if _indir(c, FFMPEG_URL, part) != FFMPEG_SHA256:
            raise AracHatasi(_hata(metin("konsol.neden_sha", konsol_dili())))
        shutil.rmtree(acilis, ignore_errors=True)
        (acilis / "bin").mkdir(parents=True)
        # Yalnızca tutulacak dosyalar çıkarılır; hepsi doğrulanmadan eski kuruluma dokunulmaz.
        cikar = [(f"bin/{n}", Path("bin") / n) for n in (*_EXELER, *_DLLER)]
        cikar.append((_LISANS, Path(_LISANS)))
        with zipfile.ZipFile(part) as z:
            for zip_ad, goreli in cikar:
                with z.open(FFMPEG_ZIP_KOK + zip_ad) as src, (acilis / goreli).open("wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
        bin_dir.mkdir(parents=True, exist_ok=True)
        # Dolu klasörün üzerine klasör olarak os.replace yapılamaz: dosyalar tek tek taşınır.
        for _, goreli in cikar:
            os.replace(acilis / goreli, ust / goreli)
        (ust / "kurulu.json").write_text(
            json.dumps({"surum": FFMPEG_SURUM, "sha256": FFMPEG_SHA256}), encoding="utf-8"
        )
        shutil.rmtree(acilis, ignore_errors=True)
        _ffmpeg_fazlalarini_sil(ust, tutulacak)
    except (AracHatasi, httpx.HTTPError, zipfile.BadZipFile, KeyError, OSError) as e:
        if eski_var:
            say(metin("konsol.ffmpeg_gecis_uyari", konsol_dili()))
            return ffmpeg, ffprobe
        if isinstance(e, AracHatasi):
            raise
        if isinstance(e, httpx.HTTPError):
            raise AracHatasi(_hata(type(e).__name__)) from e
        if isinstance(e, (zipfile.BadZipFile, KeyError)):
            raise AracHatasi(_hata(metin("konsol.neden_arsiv", konsol_dili()))) from e
        raise AracHatasi(
            _hata(metin("konsol.neden_yazilamadi", konsol_dili(), tur=type(e).__name__))
        ) from e
    finally:
        if own_client:
            c.close()
        _sil(part)
        shutil.rmtree(acilis, ignore_errors=True)
    return ffmpeg, ffprobe


def ensure_js_ortami(
    root: Path, *, client: httpx.Client | None = None, say=print
) -> Path | None:
    """quickjs-ng'yi tools/js/qjs.exe olarak kurar; hata olursa istisna atmaz, None döner."""
    dizin = root / "tools" / "js"
    hedef = dizin / "qjs.exe"
    if hedef.is_file():
        try:
            tamam = hashlib.sha256(hedef.read_bytes()).hexdigest() == JS_SHA256
        except OSError:
            tamam = False
        if tamam:
            return hedef
        _sil(hedef)

    dil = konsol_dili()
    say(metin("konsol.js_kuruluyor", dil))
    part = dizin / "qjs-indirme.part"
    own_client = client is None
    c = client
    try:
        dizin.mkdir(parents=True, exist_ok=True)
        if c is None:
            c = _yeni_istemci()
        if _indir(c, JS_URL, part) != JS_SHA256:
            raise AracHatasi(metin("konsol.neden_sha", dil))
        os.replace(part, hedef)
        return hedef
    except (AracHatasi, httpx.HTTPError, OSError) as e:
        say(metin("konsol.js_uyari", dil))
        neden = str(e) if isinstance(e, AracHatasi) else type(e).__name__
        say(metin("konsol.ayrinti", dil, neden=neden))
        return None
    finally:
        if own_client and c is not None:
            c.close()
        _sil(part)


INSTAPULLER_SURUM = "0.3.0"
INSTAPULLER_URL = (
    "https://github.com/MertOzyalcin/instapuller/releases/download/v0.3.0/"
    "instapuller-0.3.0.zip"
)
# Sürüm notundaki zip SHA-256 değeri (KT2 sözleşme kaydı).
INSTAPULLER_SHA256 = "470cb0fe937198d869843446168fdae4f4d19188a92239bf7667a11e4ed48107"
INSTAPULLER_KLASOR = "instapuller-0.3.0"

def _instapuller_kurulu_mu(dizin: Path) -> bool:
    try:
        d = json.loads((dizin / "kurulu.json").read_text(encoding="utf-8"))
        return (
            d.get("surum") == INSTAPULLER_SURUM
            and d.get("sha256") == INSTAPULLER_SHA256
            and (dizin / "venv" / "Scripts" / "python.exe").is_file()
        )
    except (OSError, ValueError, AttributeError):
        return False


def _guvenli_zip_yolu(ad: str) -> PurePosixPath:
    """Zip girdisinin yalnızca `instapuller-0.3.0/` altında ve göreli olmasını şart koşar."""
    if ad.startswith(("/", "\\")) or "\\" in ad or (len(ad) > 1 and ad[1] == ":"):
        raise AracHatasi("mutlak ya da geçersiz yol")
    p = PurePosixPath(ad)
    if ".." in p.parts or not p.parts or p.parts[0] != INSTAPULLER_KLASOR:
        raise AracHatasi("beklenmeyen arşiv yolu")
    return p


def _instapuller_ac(zip_yolu: Path, hedef: Path) -> None:
    hedef_kok = hedef.resolve()
    with zipfile.ZipFile(zip_yolu) as z:
        girdiler = [(i, _guvenli_zip_yolu(i.filename)) for i in z.infolist()]
        for bilgi, p in girdiler:
            cikis = hedef.joinpath(*p.parts)
            if not cikis.resolve().is_relative_to(hedef_kok):
                raise AracHatasi("arşiv yolu dışarı çıkıyor")
            if bilgi.is_dir():
                cikis.mkdir(parents=True, exist_ok=True)
                continue
            cikis.parent.mkdir(parents=True, exist_ok=True)
            with z.open(bilgi) as src, cikis.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)


def ensure_instapuller(
    root: Path,
    *,
    client: httpx.Client | None = None,
    run=subprocess.run,
    say=print,
) -> bool:
    """instapuller release'ini tools/instapuller altına kurar; hata olursa istisna atmaz."""
    dizin = root / "tools" / "instapuller"
    if _instapuller_kurulu_mu(dizin):
        return True

    say(metin("konsol.ip_kuruluyor", konsol_dili()))
    part = dizin / "instapuller-indirme.part"
    acilis = dizin / "_acilis"
    kaynak = dizin / INSTAPULLER_KLASOR
    own_client = client is None
    c = client
    try:
        dizin.mkdir(parents=True, exist_ok=True)
        if c is None:
            c = httpx.Client(
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, read=60.0),
                verify=tls.ssl_context(),
            )
        h = hashlib.sha256()
        with c.stream("GET", INSTAPULLER_URL) as r:
            r.raise_for_status()
            with part.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    h.update(chunk)
                    f.write(chunk)
        if h.hexdigest() != INSTAPULLER_SHA256:
            raise AracHatasi(metin("konsol.neden_sha", konsol_dili()))
        shutil.rmtree(acilis, ignore_errors=True)
        acilis.mkdir()
        _instapuller_ac(part, acilis)
        if not (acilis / INSTAPULLER_KLASOR).is_dir():
            raise AracHatasi("arşiv boş")
        shutil.rmtree(kaynak, ignore_errors=True)
        _sil(dizin / "kurulu.json")
        os.replace(acilis / INSTAPULLER_KLASOR, kaynak)
        for eski in dizin.glob("instapuller-*"):
            if eski.is_dir() and eski.name != INSTAPULLER_KLASOR:
                shutil.rmtree(eski, ignore_errors=True)

        env = os.environ.copy()
        env.update(
            UV_PROJECT_ENVIRONMENT=str(dizin / "venv"),
            UV_PYTHON_INSTALL_DIR=str(root / "tools" / "python"),
            UV_CACHE_DIR=str(root / "tools" / "uv-cache"),
            UV_PYTHON_PREFERENCE="only-managed",
            UV_PYTHON_DOWNLOADS="never",
            UV_SYSTEM_CERTS="1",
        )
        komut = [
            str(root / "tools" / "uv" / "uv.exe"),
            "sync", "--frozen", "--no-dev", "--no-install-project", "--no-build",
            "--python", "3.14",
        ]
        sonuc = run(komut, cwd=str(kaynak), env=env)
        if sonuc.returncode != 0:
            raise AracHatasi(f"uv sync çıkış kodu {sonuc.returncode}")
        (dizin / "kurulu.json").write_text(
            json.dumps({"surum": INSTAPULLER_SURUM, "sha256": INSTAPULLER_SHA256}),
            encoding="utf-8",
        )
        return True
    except (AracHatasi, httpx.HTTPError, zipfile.BadZipFile, OSError, ValueError) as e:
        dil = konsol_dili()
        say(metin("konsol.ip_uyari", dil))
        neden = f"{type(e).__name__}: {e}" if isinstance(e, AracHatasi) else type(e).__name__
        say(metin("konsol.ayrinti", dil, neden=neden))
        return False
    finally:
        if own_client and c is not None:
            c.close()
        _sil(part)
        shutil.rmtree(acilis, ignore_errors=True)
