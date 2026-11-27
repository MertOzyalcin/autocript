"""Sahte `python -m instapuller fetch ...`: SAHTE_IP_SENARYO'ya göre davranır.

Ortam: SAHTE_IP_KIND (meta.kind), SAHTE_IP_MESAJ/DETAY (hata), SAHTE_IP_STDERR (her çağrıda stderr).
Senaryolar: ok, hata:<KOD>, bozuk_json, bos, rc2, rc130, uyu, disari_yol, stderr_gurultu.
Her çağrıda argümanlar ve ortamdan ilgili değişkenler SAHTE_IP_ARGS dosyasına JSON yazılır.
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path


def _arg(ad):
    argv = sys.argv
    return argv[argv.index(ad) + 1] if ad in argv else None


def _kaydet():
    hedef = os.environ.get("SAHTE_IP_ARGS")
    if not hedef:
        return
    kayit = {
        "argv": sys.orig_argv[1:],
        "env": {
            k: os.environ.get(k)
            for k in ("PYTHONPATH", "PYTHONUTF8", "INSTAPULLER_STATE_FILE", "INSTAPULLER_PYTHON",
                      "INSTAPULLER_SRC", "FFPROBE_BIN")
        },
        "cwd": os.getcwd(),
    }
    Path(hedef).write_text(json.dumps(kayit, ensure_ascii=False), encoding="utf-8")


def _basari(video):
    url = sys.argv[-1]
    youtube = "youtube.com" in url
    kind = os.environ.get("SAHTE_IP_KIND") or ("youtube" if youtube else "instagram")
    platform_id = (
        url.split("v=", 1)[1].split("&", 1)[0] if youtube and "v=" in url else url.rstrip("/").rsplit("/", 1)[-1]
    )
    sure_env = os.environ.get("SAHTE_IP_DURATION")
    if sure_env == "null":
        sure = None
    elif sure_env is not None:
        sure = float(sure_env)
    else:
        sure = 3.0
    return json.dumps(
        {
            "ok": True,
            "video_path": str(video),
            "keep_video": False,
            "meta": {
                "kind": kind,
                "url": url,
                "platform_id": platform_id,
                "title": "Türkçe başlık: ğüşiöç İĞÜŞÖÇ",
                "author": "Kanal" if youtube else "Instagram",
                "published_at": "2022-08-26T15:53:51Z",
                "duration_s": sure,
                "stats": {"views": None, "likes": 972107, "comments": 15704},
            },
        },
        ensure_ascii=False,
    )


def _gunluk_yaz(baslangic: float, senaryo: str) -> None:
    hedef = os.environ.get("SAHTE_IP_LOG")
    if not hedef:
        return
    satir = json.dumps(
        {
            "start": baslangic,
            "end": time.monotonic(),
            "url": sys.argv[-1],
            "argv": sys.argv[1:],
            "senaryo": senaryo,
        },
        ensure_ascii=False,
    )
    with Path(hedef).open("a", encoding="utf-8") as f:
        f.write(satir + "\n")


def main():
    baslangic = time.monotonic()
    _kaydet()
    senaryo = os.environ.get("SAHTE_IP_SENARYO", "ok")
    out_dir = Path(_arg("--out-dir") or ".")
    kaynak_video = Path(os.environ.get("SAHTE_IP_VIDEO", ""))
    gecikme = float(os.environ.get("SAHTE_IP_GECIKME_S", "0") or 0)

    if os.environ.get("SAHTE_IP_STDERR"):
        print(os.environ["SAHTE_IP_STDERR"], file=sys.stderr)
    try:
        if gecikme > 0:
            time.sleep(gecikme)
        if senaryo in ("ok", "stderr_gurultu"):
            if senaryo == "stderr_gurultu":
                for i in range(50):
                    print(f"UYARI satir {i}", file=sys.stderr)
            hedef = out_dir / ("ip_x" + kaynak_video.suffix)
            shutil.copyfile(kaynak_video, hedef)
            print(_basari(hedef))
            return 0
        if senaryo.startswith("hata:"):
            kod = senaryo.split(":", 1)[1]
            print(json.dumps({"ok": False, "error": {
                "code": kod, "message": os.environ.get("SAHTE_IP_MESAJ", "SAHTE MESAJ"),
                "upload_fallback": False,
                "detail": os.environ.get("SAHTE_IP_DETAY", f"sahte detail {kod}")}}))
            return 1
        if senaryo == "bozuk_json":
            print("{bu json degil")
            return 0
        if senaryo == "bos":
            return 0
        if senaryo == "rc2":
            print("kullanim hatasi", file=sys.stderr)
            return 2
        if senaryo == "rc130":
            return 130
        if senaryo == "uyu":
            time.sleep(60)
            return 0
        if senaryo == "disari_yol":
            hedef = out_dir.resolve().parent / ("disari" + kaynak_video.suffix)
            shutil.copyfile(kaynak_video, hedef)
            print(_basari(hedef))
            return 0
        print(f"bilinmeyen senaryo: {senaryo}", file=sys.stderr)
        return 3
    finally:
        _gunluk_yaz(baslangic, senaryo)


if __name__ == "__main__":
    sys.exit(main())
