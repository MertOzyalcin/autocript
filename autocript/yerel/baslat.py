"""Başlatıcı: ffmpeg'i hazırlar, boş port seçer, oturum şifresi üretir, sunucuyu ve tarayıcıyı açar."""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

import httpx
import uvicorn

from autocript.config import ROOT, load_settings
from autocript.web.app import create_app
from autocript.yerel.araclar import AracHatasi, ensure_ffmpeg, ensure_instapuller, ensure_js_ortami
from autocript.metinler import konsol_dili, metin
from autocript.yerel.guvenlik import Oturum, cookie_name

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
BEKLEME_ARALIGI_S = 1.0
BEKLEME_ZAMAN_ASIMI_S = 15 * 60.0


def acquire_lock(path: Path) -> int | None:
    """Süreç ömrü boyunca tutulan dışlayıcı kilit; başkası tutuyorsa None döner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def release_lock(fd: int) -> None:
    try:
        try:
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except ImportError:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        os.close(fd)


def pick_socket(start: int = 8000, count: int = 20) -> socket.socket:
    """127.0.0.1 üzerinde ilk boş porta bağlı bir soket döndürür (uvicorn'a verilir)."""
    for port in range(start, start + count):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Windows'ta SO_REUSEADDR başka bir sokete portu çaldırır; kullanılmaz.
            excl = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if excl is not None:
                s.setsockopt(socket.SOL_SOCKET, excl, 1)
            s.bind((HOST, port))
        except OSError:
            s.close()
            continue
        return s
    raise AracHatasi(
        metin("konsol.port_yok", konsol_dili(), bas=str(start), son=str(start + count - 1))
    )


def app_url(port: int, token: str) -> str:
    return f"http://{HOST}:{port}/?t={token}"


def write_instance(path: Path, port: int, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"port": port, "token": token}), encoding="utf-8")


def read_instance(path: Path) -> tuple[int, str] | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        port, token = d["port"], d["token"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(port, int) or not isinstance(token, str) or not token:
        return None
    return port, token


def instance_alive(port: int, token: str) -> bool:
    try:
        r = httpx.get(
            f"http://{HOST}:{port}/api/saglik",
            cookies={cookie_name(port): token},
            timeout=1.0,
            trust_env=False,
        )
        return r.status_code == 200 and r.json().get("ok") is True
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


def _izle(server, stop: threading.Event, acil) -> None:
    """Sunucu ayağa kalkınca bir kez `acil()` çağırır."""
    while not stop.is_set():
        if getattr(server, "started", False):
            acil()
            return
        stop.wait(0.05)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="autocript")
    ap.add_argument("--tarayici-yok", action="store_true", help=metin("konsol.yardim_tarayici_yok", konsol_dili()))
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx her isteğin tam adresini INFO'da yazar (imzalı indirme linkleri dahil).
    for ad in ("httpx", "httpcore"):
        logging.getLogger(ad).setLevel(logging.WARNING)
    try:
        return _calistir(args.tarayici_yok)
    except AracHatasi as e:
        print(str(e))
        return 1


def _calistir(tarayici_yok: bool) -> int:
    settings = load_settings()
    instance_path = settings.media_dir / "oturum.json"

    var = read_instance(instance_path)
    if var is not None and instance_alive(*var):
        print(metin("konsol.zaten_acik", konsol_dili()))
        if not tarayici_yok:
            webbrowser.open(app_url(*var))
        return 0

    lock_path = settings.media_dir / "baslat.lock"
    lock_fd = acquire_lock(lock_path)
    if lock_fd is None:
        return _baska_acilisi_bekle(instance_path, tarayici_yok, lock_path)
    try:
        return _sunucu_calistir(settings, instance_path, tarayici_yok)
    finally:
        release_lock(lock_fd)


def _baska_acilisi_bekle(instance_path: Path, tarayici_yok: bool, lock_path: Path) -> int:
    print(metin("konsol.zaten_aciliyor", konsol_dili()))
    bitis = time.monotonic() + BEKLEME_ZAMAN_ASIMI_S
    while True:
        var = read_instance(instance_path)
        if var is not None and instance_alive(*var):
            if not tarayici_yok:
                webbrowser.open(app_url(*var))
            return 0
        sahip = acquire_lock(lock_path)
        if sahip is not None:
            release_lock(sahip)
            print(metin("konsol.diger_durdu", konsol_dili()))
            return 1
        if time.monotonic() >= bitis:
            break
        time.sleep(BEKLEME_ARALIGI_S)
    print(metin("konsol.diger_tamamlanmadi", konsol_dili()))
    return 1


def _sunucu_calistir(settings, instance_path: Path, tarayici_yok: bool) -> int:
    ffmpeg, ffprobe = ensure_ffmpeg(ROOT)
    # Başarısızlık açılışı durdurmaz: uyarıyı fonksiyon basar, dosya yükleme çalışır.
    ensure_instapuller(ROOT)
    ensure_js_ortami(ROOT)
    if settings.ffmpeg_bin == "ffmpeg":
        settings.ffmpeg_bin = str(ffmpeg)
    if settings.ffprobe_bin == "ffprobe":
        settings.ffprobe_bin = str(ffprobe)

    sock = pick_socket()
    port = sock.getsockname()[1]
    stop = threading.Event()
    watcher: threading.Thread | None = None
    yazildi = False
    try:
        oturum = Oturum.yeni(port)
        app = create_app(settings, oturum=oturum, env_path=ROOT / ".env")
        server = uvicorn.Server(uvicorn.Config(app, access_log=False))

        def acildi() -> None:
            nonlocal yazildi
            acildi_mi = False
            try:
                write_instance(instance_path, port, oturum.token)
                yazildi = True
                print(metin("konsol.uygulama_acik", konsol_dili()))
                if tarayici_yok:
                    return
                acildi_mi = bool(webbrowser.open(app_url(port, oturum.token)))
            except Exception:
                log.exception("Tarayıcı açılışı başarısız")
            if not acildi_mi:
                print(metin("konsol.tarayici_acilmadi", konsol_dili()))

        watcher = threading.Thread(target=_izle, args=(server, stop, acildi), daemon=True)
        watcher.start()
        server.run(sockets=[sock])
    finally:
        stop.set()
        if watcher is not None:
            watcher.join(timeout=2)
        sock.close()
        if yazildi:
            try:
                instance_path.unlink()
            except OSError:
                pass
    return 0
