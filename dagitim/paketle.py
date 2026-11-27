"""Dağıtım zip'ini üretir: izin verilen yollardan `git archive` ve sızıntı denetimi.

Çalıştırma: uv run python dagitim/paketle.py  (çıktı: dist/)
"""

import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ALLOW: list[str] = [
    "autocript/",
    "schema/",
    "pyproject.toml",
    "uv.lock",
    "baslat.cmd",
    "KURULUM.md",
    "BENIOKU.txt",
    "README.txt",
    "dagitim/uv-indir.ps1",
]

PREFIX = "video-transkript/"

_YASAK_PARCALAR = {
    "data", "tools", ".venv", "experiments", "tests", "reviews", "docs",
    ".claude", ".superpowers", "__pycache__",
}
_YASAK_UZANTILAR = {
    ".mp4", ".mov", ".webm", ".mkv", ".m4a", ".mp3", ".wav", ".aac", ".flac",
    ".db", ".db-wal", ".db-shm", ".zip",
}


def violations(names: list[str]) -> list[str]:
    """Kurallara uymayan adları döndürür."""
    kotu: list[str] = []
    for ad in names:
        yol = PurePosixPath(ad.replace("\\", "/"))
        dosya = yol.name
        if (
            dosya == ".env"
            or dosya.startswith(".env.")
            or any(p in _YASAK_PARCALAR for p in yol.parts)
            or yol.suffix.lower() in _YASAK_UZANTILAR
        ):
            kotu.append(ad)
    return kotu


def _git(repo: Path, *args: str) -> str:
    sonuc = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return sonuc.stdout


def build_zip(repo: Path, out_dir: Path, ref: str = "HEAD") -> Path:
    repo = Path(repo)
    out_dir = Path(out_dir)
    try:
        degisen = _git(repo, "status", "--porcelain", "--", *ALLOW)
    except subprocess.CalledProcessError as hata:
        raise RuntimeError("Git durumu okunamadı.") from hata
    if degisen.strip():
        raise RuntimeError(
            "İzinli yollarda commit edilmemiş değişiklik var. Önce commit edin."
        )

    surum = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    hedef: Path | None = None
    try:
        sha = _git(repo, "rev-parse", "--short", ref).strip()
        out_dir.mkdir(parents=True, exist_ok=True)
        hedef = out_dir / f"video-transkript-{surum}-{sha}.zip"
        _git(
            repo, "archive", "--format=zip", f"--prefix={PREFIX}",
            "-o", str(hedef.resolve()), ref, "--", *ALLOW,
        )
    except subprocess.CalledProcessError as hata:
        if hedef is not None:
            hedef.unlink(missing_ok=True)
        raise RuntimeError("Zip üretilemedi.") from hata

    sorun = _denetle(hedef)
    if sorun:
        hedef.unlink(missing_ok=True)
        raise RuntimeError(sorun)
    return hedef


def _denetle(zip_yolu: Path) -> str | None:
    with zipfile.ZipFile(zip_yolu) as z:
        adlar = z.namelist()
        kotu = violations(adlar)
        if kotu:
            return "Zip'te yasak dosyalar var: " + ", ".join(kotu)
        try:
            cmd = z.read(PREFIX + "baslat.cmd")
        except KeyError:
            return "Zip'te baslat.cmd yok."
    if not cmd.endswith(b"\r\n"):
        return "baslat.cmd satır sonları CRLF değil."
    return None


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    try:
        yol = build_zip(repo, repo / "dist")
    except RuntimeError as hata:
        print(hata, file=sys.stderr)
        return 1
    print(yol)
    return 0


if __name__ == "__main__":
    sys.exit(main())
