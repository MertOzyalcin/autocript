import subprocess
import zipfile
from pathlib import Path

import pytest

from dagitim.paketle import ALLOW, build_zip, violations


def test_violations():
    ihlal = [
        ".env",
        "video-transkript/.env.local",
        "data/media/a.mp4",
        "tests/x.py",
        "autocript/__pycache__/a.pyc",
    ]
    assert violations(ihlal) == ihlal
    temiz = ["autocript/web/app.py", "video-transkript/baslat.cmd", "KURULUM.md"]
    assert violations(temiz) == []


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _depo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    dosyalar = {
        "autocript/__init__.py": "",
        "schema/transcript-v1.json": "{}",
        "pyproject.toml": '[project]\nname = "x"\nversion = "9.9.9"\n',
        "uv.lock": "",
        "KURULUM.md": "# kurulum\n",
        "BENIOKU.txt": "benioku\r\n",
        "README.txt": "readme\r\n",
        "dagitim/uv-indir.ps1": "x\r\n",
        "tests/a.py": "",
        "experiments/b.py": "",
    }
    for ad, icerik in dosyalar.items():
        p = repo / ad
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(icerik.encode())
    (repo / "baslat.cmd").write_bytes(b"@echo off\r\n")
    (repo / ".gitattributes").write_text("*.cmd text eol=crlf\n*.txt text eol=crlf\n")
    (repo / ".env").write_text("SECRET=1\n")
    _git(repo, "add", "-f", "--", *dosyalar, "baslat.cmd", ".gitattributes")
    _git(repo, "commit", "-q", "-m", "ilk")
    return repo


def test_build_zip_yalnizca_izinliler(tmp_path):
    repo = _depo(tmp_path)
    out = tmp_path / "dist"
    zip_yolu = build_zip(repo, out)
    assert zip_yolu.parent == out
    assert zip_yolu.name.startswith("video-transkript-9.9.9-")
    with zipfile.ZipFile(zip_yolu) as z:
        adlar = [a for a in z.namelist() if not a.endswith("/")]
    assert adlar
    for ad in adlar:
        assert ad.startswith("video-transkript/")
        yol = ad[len("video-transkript/"):]
        assert any(yol == a or yol.startswith(a) for a in ALLOW), ad
    assert "video-transkript/BENIOKU.txt" in adlar
    assert "video-transkript/README.txt" in adlar
    assert not any(".env" in a or "tests/" in a or "experiments/" in a for a in adlar)


def test_build_zip_commitsiz_degisiklik_reddedilir(tmp_path):
    repo = _depo(tmp_path)
    (repo / "KURULUM.md").write_text("# degisti\n")
    with pytest.raises(RuntimeError):
        build_zip(repo, tmp_path / "dist")


def test_build_zip_arsiv_basarisizsa_kismi_zip_silinir(tmp_path, monkeypatch):
    from dagitim import paketle

    repo = _depo(tmp_path)
    gercek = paketle._git

    def sahte(repo_, *args):
        if args and args[0] == "archive":
            Path(args[args.index("-o") + 1]).write_bytes(b"PK kismi")
            raise subprocess.CalledProcessError(1, "git archive")
        return gercek(repo_, *args)

    monkeypatch.setattr(paketle, "_git", sahte)
    out = tmp_path / "dist"
    with pytest.raises(RuntimeError, match="Zip üretilemedi"):
        build_zip(repo, out)
    assert list(out.glob("*.zip")) == []
