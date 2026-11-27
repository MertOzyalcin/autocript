import hashlib
import io
import json
import socket
import zipfile

import httpx
import pytest

from autocript.yerel import araclar
from autocript.yerel.araclar import AracHatasi, ensure_ffmpeg


DLLER = (
    "avcodec-63.dll", "avdevice-63.dll", "avfilter-12.dll", "avformat-63.dll",
    "avutil-61.dll", "swresample-7.dll", "swscale-10.dll",
)
KOK = araclar.FFMPEG_ZIP_KOK


def _zip_bytes() -> bytes:
    """BtbN shared düzeni: 2 exe + 7 dll + ffplay, doc/include/lib/presets, LICENSE.txt."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{KOK}bin/ffmpeg.exe", b"FFMPEG")
        z.writestr(f"{KOK}bin/ffprobe.exe", b"FFPROBE")
        z.writestr(f"{KOK}bin/ffplay.exe", b"FFPLAY")
        for d in DLLER:
            z.writestr(f"{KOK}bin/{d}", b"DLL " + d.encode())
        z.writestr(f"{KOK}LICENSE.txt", b"LGPL")
        z.writestr(f"{KOK}doc/a.txt", b"doc")
        z.writestr(f"{KOK}include/x.h", b"h")
        z.writestr(f"{KOK}lib/x.lib", b"l")
        z.writestr(f"{KOK}presets/p.ffpreset", b"p")
    return buf.getvalue()


def _ff_kurulu_yaz(root, *, kayit=True, sha=None):
    """Tam ve kayıtlı bir shared kurulum hazırlar."""
    b = _bin(root)
    b.mkdir(parents=True, exist_ok=True)
    (b / "ffmpeg.exe").write_bytes(b"x")
    (b / "ffprobe.exe").write_bytes(b"y")
    for d in DLLER:
        (b / d).write_bytes(b"d")
    (b.parent / "LICENSE.txt").write_bytes(b"l")
    if kayit:
        (b.parent / "kurulu.json").write_text(
            json.dumps({"surum": araclar.FFMPEG_SURUM, "sha256": sha or araclar.FFMPEG_SHA256}),
            encoding="utf-8",
        )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def _bin(root):
    return root / "tools" / "ffmpeg" / "bin"


def test_ffmpeg_kurulu_agsiz(tmp_path):
    _ff_kurulu_yaz(tmp_path)
    b = _bin(tmp_path)

    def handler(request):
        pytest.fail("ağa çıkılmamalı")

    ff, fp = ensure_ffmpeg(tmp_path, client=_client(handler), say=lambda *_: None)
    assert ff == b / "ffmpeg.exe" and fp == b / "ffprobe.exe"


def test_ffmpeg_indirir_ve_cikarir(tmp_path, monkeypatch):
    data = _zip_bytes()
    monkeypatch.setattr(araclar, "FFMPEG_SHA256", hashlib.sha256(data).hexdigest())
    ff, fp = ensure_ffmpeg(
        tmp_path,
        client=_client(lambda r: httpx.Response(200, content=data)),
        say=lambda *_: None,
    )
    assert ff.read_bytes() == b"FFMPEG" and fp.read_bytes() == b"FFPROBE"
    assert not (_bin(tmp_path) / "ffplay.exe").exists()
    assert not list((tmp_path / "tools").glob("*.part"))
    assert not list(_bin(tmp_path).glob("*.tmp"))
    assert not (tmp_path / "tools" / "ffmpeg" / "_acilis").exists()


def test_ffmpeg_hash_uyusmaz_temizler(tmp_path, monkeypatch):
    monkeypatch.setattr(araclar, "FFMPEG_SHA256", "0" * 64)
    with pytest.raises(AracHatasi, match="ffmpeg indirilemedi") as ei:
        ensure_ffmpeg(
            tmp_path,
            client=_client(lambda r: httpx.Response(200, content=_zip_bytes())),
            say=lambda *_: None,
        )
    assert "(ayrıntı: SHA-256 eşleşmedi)" in str(ei.value)
    assert not _bin(tmp_path).exists() or not list(_bin(tmp_path).glob("*"))
    assert not list((tmp_path / "tools").glob("*.part"))


def test_ffmpeg_indirme_kesilir_temizler(tmp_path):
    class Kesik(httpx.SyncByteStream):
        def __iter__(self):
            yield b"PK\x03\x04"
            raise httpx.ReadError("kesildi")

    with pytest.raises(AracHatasi, match="ffmpeg indirilemedi") as ei:
        ensure_ffmpeg(
            tmp_path,
            client=_client(lambda r: httpx.Response(200, stream=Kesik())),
            say=lambda *_: None,
        )
    assert "(ayrıntı: ReadError)" in str(ei.value)
    assert not list((tmp_path / "tools").glob("*.part"))


def test_ffmpeg_disk_hatasi_ayrintisi(tmp_path, monkeypatch):
    data = _zip_bytes()
    monkeypatch.setattr(araclar, "FFMPEG_SHA256", hashlib.sha256(data).hexdigest())

    def boz(*a, **k):
        raise PermissionError("erisim yok gizli-yol")

    monkeypatch.setattr(araclar.os, "replace", boz)
    with pytest.raises(AracHatasi, match="ffmpeg indirilemedi") as ei:
        ensure_ffmpeg(
            tmp_path,
            client=_client(lambda r: httpx.Response(200, content=data)),
            say=lambda *_: None,
        )
    assert "(ayrıntı: dosya yazılamadı: PermissionError)" in str(ei.value)
    assert "gizli" not in str(ei.value)


def test_ffmpeg_bozuk_arsiv_ayrintisi(tmp_path, monkeypatch):
    data = b"bu bir zip degil"
    monkeypatch.setattr(araclar, "FFMPEG_SHA256", hashlib.sha256(data).hexdigest())
    with pytest.raises(AracHatasi, match="ffmpeg indirilemedi") as ei:
        ensure_ffmpeg(
            tmp_path,
            client=_client(lambda r: httpx.Response(200, content=data)),
            say=lambda *_: None,
        )
    assert "(ayrıntı: arşiv bozuk)" in str(ei.value)


def test_ffmpeg_turkce_bosluklu_yol(tmp_path, monkeypatch):
    root = tmp_path / "Çalışma Ağacı klasörü" / "video transkript"
    root.mkdir(parents=True)
    data = _zip_bytes()
    monkeypatch.setattr(araclar, "FFMPEG_SHA256", hashlib.sha256(data).hexdigest())
    ff, fp = ensure_ffmpeg(
        root,
        client=_client(lambda r: httpx.Response(200, content=data)),
        say=lambda *_: None,
    )
    assert ff.is_file() and fp.is_file()


def _bos_taban_port() -> int:
    for base in range(20000, 60000, 7):
        socks = []
        try:
            for p in (base, base + 1, base + 2):
                s = socket.socket()
                s.bind(("127.0.0.1", p))
                socks.append(s)
            return base
        except OSError:
            continue
        finally:
            for s in socks:
                s.close()
    pytest.skip("boş port yok")


def test_port_dolu_sonrakini_secer():
    from autocript.yerel.baslat import pick_socket

    base = _bos_taban_port()
    tutan = socket.socket()
    tutan.bind(("127.0.0.1", base))
    tutan.listen()
    try:
        s = pick_socket(base, 3)
        try:
            assert s.getsockname() == ("127.0.0.1", base + 1)
        finally:
            s.close()
    finally:
        tutan.close()


def test_uc_port_da_doluysa_arac_hatasi():
    from autocript.yerel.baslat import pick_socket

    base = _bos_taban_port()
    tutanlar = []
    try:
        for p in (base, base + 1, base + 2):
            t = socket.socket()
            t.bind(("127.0.0.1", p))
            t.listen()
            tutanlar.append(t)
        with pytest.raises(AracHatasi):
            pick_socket(base, 3)
    finally:
        for t in tutanlar:
            t.close()


# --- ensure_instapuller ---------------------------------------------------

import subprocess
from pathlib import Path

K = araclar.INSTAPULLER_KLASOR


def _ip_zip(ekstra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{K}/pyproject.toml", b"[project]\nname='instapuller'\n")
        z.writestr(f"{K}/uv.lock", b"version = 1\n")
        z.writestr(f"{K}/instapuller/__init__.py", b"")
        for ad, v in (ekstra or {}).items():
            z.writestr(ad, v)
    return buf.getvalue()


def _ip_hazirla(monkeypatch, veri: bytes) -> httpx.Client:
    monkeypatch.setattr(araclar, "INSTAPULLER_SHA256", hashlib.sha256(veri).hexdigest())
    return _client(lambda req: httpx.Response(200, content=veri))


class _Run:
    def __init__(self, kod: int = 0):
        self.kod = kod
        self.cagrilar: list[tuple[list, dict]] = []

    def __call__(self, cmd, **kw):
        self.cagrilar.append((list(cmd), kw))
        return subprocess.CompletedProcess(cmd, self.kod)


def _ip(root) -> Path:
    return root / "tools" / "instapuller"


def test_instapuller_kurar(tmp_path, monkeypatch):
    c = _ip_hazirla(monkeypatch, _ip_zip())
    run = _Run(0)
    mesaj: list[str] = []
    assert araclar.ensure_instapuller(tmp_path, client=c, run=run, say=mesaj.append) is True
    kaynak = _ip(tmp_path) / K
    assert (kaynak / "pyproject.toml").is_file()
    (cmd, kw), = run.cagrilar
    assert cmd == [
        str(tmp_path / "tools" / "uv" / "uv.exe"),
        "sync", "--frozen", "--no-dev", "--no-install-project", "--no-build",
        "--python", "3.14",
    ]
    assert Path(kw["cwd"]) == kaynak
    env = kw["env"]
    assert env["UV_PROJECT_ENVIRONMENT"] == str(_ip(tmp_path) / "venv")
    assert env["UV_PYTHON_INSTALL_DIR"] == str(tmp_path / "tools" / "python")
    assert env["UV_CACHE_DIR"] == str(tmp_path / "tools" / "uv-cache")
    assert env["UV_PYTHON_DOWNLOADS"] == "never"
    assert env["UV_PYTHON_PREFERENCE"] == "only-managed"
    assert env["UV_SYSTEM_CERTS"] == "1"
    for k in ("UV_PROJECT_ENVIRONMENT", "UV_PYTHON_INSTALL_DIR", "UV_CACHE_DIR"):
        assert Path(env[k]).is_absolute()
    d = json.loads((_ip(tmp_path) / "kurulu.json").read_text(encoding="utf-8"))
    assert d["sha256"] == araclar.INSTAPULLER_SHA256
    assert not list(_ip(tmp_path).glob("*.part")) and not (_ip(tmp_path) / "_acilis").exists()


def test_instapuller_yarim_kurulumdan_sonra_yeniden_dener(tmp_path, monkeypatch):
    c = _ip_hazirla(monkeypatch, _ip_zip())
    assert araclar.ensure_instapuller(tmp_path, client=c, run=_Run(1), say=lambda m: None) is False
    assert (_ip(tmp_path) / K).is_dir()
    assert araclar.ensure_instapuller(tmp_path, client=c, run=_Run(0), say=lambda m: None) is True
    assert (_ip(tmp_path) / K / "pyproject.toml").is_file()
    assert not (_ip(tmp_path) / K / K).exists()


def test_instapuller_kuruluysa_atlar(tmp_path, monkeypatch):
    monkeypatch.setattr(araclar, "INSTAPULLER_SHA256", "ab" * 32)
    ip = _ip(tmp_path)
    (ip / "venv" / "Scripts").mkdir(parents=True)
    (ip / "venv" / "Scripts" / "python.exe").write_bytes(b"")
    (ip / "kurulu.json").write_text(
        json.dumps({"surum": araclar.INSTAPULLER_SURUM, "sha256": "ab" * 32}), encoding="utf-8"
    )

    def yasak(*a, **k):
        pytest.fail("çağrılmamalı")

    c = _client(yasak)
    assert araclar.ensure_instapuller(tmp_path, client=c, run=yasak, say=yasak) is True


def test_instapuller_hash_uyusmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(araclar, "INSTAPULLER_SHA256", "00" * 32)
    c = _client(lambda req: httpx.Response(200, content=_ip_zip()))
    run = _Run(0)
    mesaj: list[str] = []
    assert araclar.ensure_instapuller(tmp_path, client=c, run=run, say=mesaj.append) is False
    ip = _ip(tmp_path)
    assert not list(ip.glob("*.part")) and not (ip / "_acilis").exists() and not (ip / K).exists()
    assert run.cagrilar == []
    assert any("Video indirme aracı kurulamadı" in m for m in mesaj)


def test_instapuller_zip_slip(tmp_path, monkeypatch):
    kok = tmp_path / "kok"
    c = _ip_hazirla(monkeypatch, _ip_zip({f"{K}/../../kotu.txt": b"x"}))
    run = _Run(0)
    assert araclar.ensure_instapuller(kok, client=c, run=run, say=lambda m: None) is False
    assert run.cagrilar == []
    assert not (kok / "kotu.txt").exists() and not (tmp_path / "kotu.txt").exists()
    assert not (_ip(kok) / "kotu.txt").exists()
    assert not (_ip(kok) / K).exists()


def test_instapuller_zip_mutlak_yol(tmp_path, monkeypatch):
    c = _ip_hazirla(monkeypatch, _ip_zip({"/mutlak.txt": b"x"}))
    assert araclar.ensure_instapuller(tmp_path, client=c, run=_Run(0), say=lambda m: None) is False


def test_instapuller_uv_hata(tmp_path, monkeypatch):
    c = _ip_hazirla(monkeypatch, _ip_zip())
    assert araclar.ensure_instapuller(tmp_path, client=c, run=_Run(1), say=lambda m: None) is False
    assert not (_ip(tmp_path) / "kurulu.json").exists()


def test_instapuller_uv_yok_istisna_atmaz(tmp_path, monkeypatch):
    c = _ip_hazirla(monkeypatch, _ip_zip())

    def run(cmd, **kw):
        raise FileNotFoundError("uv.exe")

    assert araclar.ensure_instapuller(tmp_path, client=c, run=run, say=lambda m: None) is False


def test_instapuller_ag_hatasi_istisna_atmaz(tmp_path):
    def h(req):
        raise httpx.ConnectError("yok")

    assert araclar.ensure_instapuller(
        tmp_path, client=_client(h), run=_Run(0), say=lambda m: None
    ) is False


def test_instapuller_turkce_bosluklu_kok(tmp_path, monkeypatch):
    kok = tmp_path / "video transkript Çalışma Ağacı"
    c = _ip_hazirla(monkeypatch, _ip_zip())
    assert araclar.ensure_instapuller(kok, client=c, run=_Run(0), say=lambda m: None) is True




def test_ffmpeg_fazlalari_siler(tmp_path):
    _ff_kurulu_yaz(tmp_path)
    b = _bin(tmp_path)
    (b / "doc").mkdir()
    (b / "presets").mkdir()
    (b / "ffplay.exe").write_bytes(b"z")
    (b / "doc" / "a.txt").write_bytes(b"d")
    (b / "presets" / "p.ffpreset").write_bytes(b"p")
    ust = tmp_path / "tools" / "ffmpeg"
    (ust / "doc").mkdir()
    (ust / "include").mkdir()
    (ust / "include" / "x.h").write_bytes(b"h")

    def handler(request):
        pytest.fail("ağa çıkılmamalı")

    ff, fp = ensure_ffmpeg(tmp_path, client=_client(handler), say=lambda *_: None)
    assert ff.read_bytes() == b"x" and fp.read_bytes() == b"y"
    assert sorted(p.name for p in ust.rglob("*")) == sorted(
        ["bin", "ffmpeg.exe", "ffprobe.exe", *DLLER, "LICENSE.txt", "kurulu.json"]
    )


def _ff_zip_sha(monkeypatch):
    data = _zip_bytes()
    monkeypatch.setattr(araclar, "FFMPEG_SHA256", hashlib.sha256(data).hexdigest())
    return data


def test_ffmpeg_shared_kurulur(tmp_path, monkeypatch):
    data = _ff_zip_sha(monkeypatch)
    ensure_ffmpeg(
        tmp_path, client=_client(lambda r: httpx.Response(200, content=data)), say=lambda *_: None
    )
    b = _bin(tmp_path)
    assert sorted(p.name for p in b.iterdir()) == sorted(["ffmpeg.exe", "ffprobe.exe", *DLLER])
    ust = b.parent
    assert (ust / "LICENSE.txt").read_bytes() == b"LGPL"
    assert json.loads((ust / "kurulu.json").read_text(encoding="utf-8")) == {
        "surum": "btbn-n9.0.2-lgpl-shared", "sha256": araclar.FFMPEG_SHA256,
    }
    assert sorted(p.name for p in ust.iterdir()) == ["LICENSE.txt", "bin", "kurulu.json"]


def test_eski_statik_kurulumdan_gecis(tmp_path, monkeypatch):
    b = _bin(tmp_path)
    b.mkdir(parents=True)
    (b / "ffmpeg.exe").write_bytes(b"ESKI")
    (b / "ffprobe.exe").write_bytes(b"ESKI")
    (b / "ffplay.exe").write_bytes(b"ESKI")
    data = _ff_zip_sha(monkeypatch)
    ff, fp = ensure_ffmpeg(
        tmp_path, client=_client(lambda r: httpx.Response(200, content=data)), say=lambda *_: None
    )
    assert ff.read_bytes() == b"FFMPEG" and fp.read_bytes() == b"FFPROBE"
    assert not (b / "ffplay.exe").exists()
    assert all((b / d).is_file() for d in DLLER)
    assert (b.parent / "kurulu.json").is_file()
    assert not (b.parent / "_acilis").exists()


def test_gecis_basarisizsa_eski_kalir(tmp_path, monkeypatch):
    b = _bin(tmp_path)
    b.mkdir(parents=True)
    (b / "ffmpeg.exe").write_bytes(b"ESKI-A")
    (b / "ffprobe.exe").write_bytes(b"ESKI-B")
    (b / "ffplay.exe").write_bytes(b"ESKI-C")
    monkeypatch.setattr(araclar, "FFMPEG_SHA256", "0" * 64)
    mesaj: list[str] = []
    ff, fp = ensure_ffmpeg(
        tmp_path,
        client=_client(lambda r: httpx.Response(200, content=_zip_bytes())),
        say=mesaj.append,
    )
    assert ff == b / "ffmpeg.exe" and fp == b / "ffprobe.exe"
    assert ff.read_bytes() == b"ESKI-A" and fp.read_bytes() == b"ESKI-B"
    assert (b / "ffplay.exe").read_bytes() == b"ESKI-C"
    assert any("ffmpeg güncellenemedi" in m for m in mesaj)
    assert not list((tmp_path / "tools").glob("*.part"))
    assert not (b.parent / "_acilis").exists()
    assert not (b.parent / "kurulu.json").exists()


def test_ffmpeg_kurulu_json_uyusmazsa_yeniden_kurar(tmp_path, monkeypatch):
    _ff_kurulu_yaz(tmp_path, sha="9" * 64)
    data = _ff_zip_sha(monkeypatch)
    ff, _ = ensure_ffmpeg(
        tmp_path, client=_client(lambda r: httpx.Response(200, content=data)), say=lambda *_: None
    )
    assert ff.read_bytes() == b"FFMPEG"


def test_ffmpeg_dll_eksikse_yeniden_kurar(tmp_path, monkeypatch):
    _ff_kurulu_yaz(tmp_path)
    (_bin(tmp_path) / DLLER[0]).unlink()
    data = _ff_zip_sha(monkeypatch)
    ensure_ffmpeg(
        tmp_path, client=_client(lambda r: httpx.Response(200, content=data)), say=lambda *_: None
    )
    assert (_bin(tmp_path) / DLLER[0]).read_bytes() == b"DLL " + DLLER[0].encode()


# --- ensure_js_ortami -----------------------------------------------------

QJS = b"QJS-EXE"


def _js_hazirla(monkeypatch, veri: bytes = QJS) -> None:
    monkeypatch.setattr(araclar, "JS_SHA256", hashlib.sha256(veri).hexdigest())


def _js(root) -> Path:
    return root / "tools" / "js"


def test_js_ortami_kurulur(tmp_path, monkeypatch):
    _js_hazirla(monkeypatch)
    mesaj: list[str] = []
    yol = araclar.ensure_js_ortami(
        tmp_path, client=_client(lambda r: httpx.Response(200, content=QJS)), say=mesaj.append
    )
    assert yol == _js(tmp_path) / "qjs.exe" and yol.read_bytes() == QJS
    assert [p.name for p in _js(tmp_path).iterdir()] == ["qjs.exe"]
    assert any("YouTube aracı kuruluyor" in m for m in mesaj)


def test_js_ortami_sha_uyusmaz(tmp_path, monkeypatch):
    _js_hazirla(monkeypatch, b"baska")
    mesaj: list[str] = []
    yol = araclar.ensure_js_ortami(
        tmp_path, client=_client(lambda r: httpx.Response(200, content=QJS)), say=mesaj.append
    )
    assert yol is None
    assert not list(_js(tmp_path).glob("*"))
    assert any("YouTube aracı kurulamadı" in m for m in mesaj)
    assert any("SHA-256 eşleşmedi" in m for m in mesaj)


def test_js_ortami_ag_hatasi_istisna_atmaz(tmp_path):
    def h(req):
        raise httpx.ConnectError("yok")

    assert araclar.ensure_js_ortami(tmp_path, client=_client(h), say=lambda m: None) is None


def test_js_ortami_kurulu_agsiz(tmp_path, monkeypatch):
    _js_hazirla(monkeypatch)
    _js(tmp_path).mkdir(parents=True)
    (_js(tmp_path) / "qjs.exe").write_bytes(QJS)

    def yasak(*a, **k):
        pytest.fail("ağa çıkılmamalı")

    yol = araclar.ensure_js_ortami(tmp_path, client=_client(yasak), say=yasak)
    assert yol == _js(tmp_path) / "qjs.exe"


def test_js_ortami_bozuk_dosya_yeniden_kurulur(tmp_path, monkeypatch):
    _js_hazirla(monkeypatch)
    _js(tmp_path).mkdir(parents=True)
    (_js(tmp_path) / "qjs.exe").write_bytes(b"BOZUK")
    yol = araclar.ensure_js_ortami(
        tmp_path, client=_client(lambda r: httpx.Response(200, content=QJS)), say=lambda m: None
    )
    assert yol is not None and yol.read_bytes() == QJS


def test_js_ortami_bozuk_dosya_kurulamazsa_silinir(tmp_path, monkeypatch):
    _js_hazirla(monkeypatch, b"baska")
    _js(tmp_path).mkdir(parents=True)
    (_js(tmp_path) / "qjs.exe").write_bytes(b"BOZUK")
    assert araclar.ensure_js_ortami(
        tmp_path, client=_client(lambda r: httpx.Response(200, content=QJS)), say=lambda m: None
    ) is None
    assert not (_js(tmp_path) / "qjs.exe").exists()


def test_js_ortami_turkce_bosluklu_kok(tmp_path, monkeypatch):
    _js_hazirla(monkeypatch)
    kok = tmp_path / "video transkript Çalışma Ağacı"
    assert araclar.ensure_js_ortami(
        kok, client=_client(lambda r: httpx.Response(200, content=QJS)), say=lambda m: None
    ) is not None


# --- instapuller v0.3.0 ---------------------------------------------------


def test_instapuller_030_kurulur(tmp_path, monkeypatch):
    assert araclar.INSTAPULLER_SURUM == "0.3.0" and K == "instapuller-0.3.0"
    eski = _ip(tmp_path) / "instapuller-0.1.0"
    eski.mkdir(parents=True)
    (eski / "pyproject.toml").write_text("x", encoding="utf-8")
    (_ip(tmp_path) / "kurulu.json").write_text(
        json.dumps({"surum": "0.1.0", "sha256": "ab" * 32}), encoding="utf-8"
    )
    c = _ip_hazirla(monkeypatch, _ip_zip())
    assert araclar.ensure_instapuller(tmp_path, client=c, run=_Run(0), say=lambda m: None) is True
    d = json.loads((_ip(tmp_path) / "kurulu.json").read_text(encoding="utf-8"))
    assert d["surum"] == "0.3.0"
    assert not eski.exists()
    assert (_ip(tmp_path) / K / "pyproject.toml").is_file()


def test_instapuller_eski_surum_kayitliysa_yeniden_kurar(tmp_path, monkeypatch):
    ip = _ip(tmp_path)
    (ip / "venv" / "Scripts").mkdir(parents=True)
    (ip / "venv" / "Scripts" / "python.exe").write_bytes(b"")
    (ip / "kurulu.json").write_text(
        json.dumps({"surum": "0.1.0", "sha256": araclar.INSTAPULLER_SHA256}), encoding="utf-8"
    )
    c = _ip_hazirla(monkeypatch, _ip_zip())
    run = _Run(0)
    assert araclar.ensure_instapuller(tmp_path, client=c, run=run, say=lambda m: None) is True
    assert len(run.cagrilar) == 1


def test_instapuller_sha_uyusmazsa_kurulmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(araclar, "INSTAPULLER_SHA256", "00" * 32)
    c = _client(lambda req: httpx.Response(200, content=_ip_zip()))
    mesaj: list[str] = []
    assert araclar.ensure_instapuller(tmp_path, client=c, run=_Run(0), say=mesaj.append) is False
    assert not list(_ip(tmp_path).glob("*.part"))
    assert any("Video indirme aracı kurulamadı" in m for m in mesaj)
