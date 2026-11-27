import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from autocript.config import Settings
from autocript.yerel import baslat
from autocript.yerel.araclar import AracHatasi

TOKEN = "T" * 43
REPO = Path(__file__).resolve().parents[2]


def test_app_url():
    assert baslat.app_url(8001, "abc") == "http://127.0.0.1:8001/?t=abc"


def test_instance_dosyasi_gidis_donus(tmp_path):
    p = tmp_path / "klasor" / "oturum.json"
    baslat.write_instance(p, 8123, TOKEN)
    assert baslat.read_instance(p) == (8123, TOKEN)
    p.write_text("bozuk{", encoding="utf-8")
    assert baslat.read_instance(p) is None
    assert baslat.read_instance(tmp_path / "yok.json") is None


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setattr(baslat, "ROOT", tmp_path)
    s = Settings(media_dir=tmp_path)
    monkeypatch.setattr(baslat, "load_settings", lambda *a, **k: s)
    acilan = []
    monkeypatch.setattr(baslat.webbrowser, "open", lambda url, *a, **k: acilan.append(url))
    return SimpleNamespace(settings=s, acilan=acilan, tmp=tmp_path)


def _ffmpeg_yasak(monkeypatch):
    def yasak(*a, **k):
        pytest.fail("ensure_ffmpeg çağrılmamalı")

    monkeypatch.setattr(baslat, "ensure_ffmpeg", yasak)
    monkeypatch.setattr(baslat, "ensure_instapuller", yasak)
    monkeypatch.setattr(baslat, "ensure_js_ortami", yasak)


class _Yasak:
    def __init__(self, *a, **k):
        pytest.fail("uvicorn başlamamalı")


def test_tek_ornek_canliysa_yeniden_kullanilir(ortam, monkeypatch):
    baslat.write_instance(ortam.tmp / "oturum.json", 8123, TOKEN)
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: True)
    _ffmpeg_yasak(monkeypatch)
    monkeypatch.setattr(baslat, "uvicorn", SimpleNamespace(Config=_Yasak, Server=_Yasak))
    assert baslat.main(["--tarayici-yok"]) == 0
    assert ortam.acilan == []
    assert baslat.main([]) == 0
    assert ortam.acilan == [baslat.app_url(8123, TOKEN)]


def test_bayat_ornek_dosyasi_yok_sayilir(ortam, monkeypatch):
    baslat.write_instance(ortam.tmp / "oturum.json", 8123, TOKEN)
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)

    def hata(root, **k):
        raise AracHatasi("ffmpeg yok")

    monkeypatch.setattr(baslat, "ensure_ffmpeg", hata)
    assert baslat.main(["--tarayici-yok"]) == 1
    assert ortam.acilan == []


def test_arac_hatasi_turkce_mesaj(ortam, monkeypatch, capsys):
    def hata(root, **k):
        raise AracHatasi("ffmpeg indirilemedi. İnternet bağlantınızı kontrol edin.")

    monkeypatch.setattr(baslat, "ensure_ffmpeg", hata)
    monkeypatch.setattr(baslat, "uvicorn", SimpleNamespace(Config=_Yasak, Server=_Yasak))
    assert baslat.main(["--tarayici-yok"]) == 1
    out = capsys.readouterr()
    assert "ffmpeg indirilemedi" in out.out + out.err
    assert "Traceback" not in out.out + out.err


def _sahte_sunucu(monkeypatch, ortam, yakala):
    ff = ortam.tmp / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    fp = ff.with_name("ffprobe.exe")
    monkeypatch.setattr(baslat, "ensure_ffmpeg", lambda root, **k: (ff, fp))
    monkeypatch.setattr(baslat, "ensure_instapuller", lambda root, **k: True)
    monkeypatch.setattr(baslat, "ensure_js_ortami", lambda root, **k: ff.with_name("qjs.exe"))

    def create_app(settings, **kw):
        yakala["settings"] = settings
        yakala["oturum"] = kw["oturum"]
        yakala["env_path"] = kw["env_path"]
        return object()

    class Server:
        def __init__(self, config):
            self.started = False

        def run(self, sockets=None):
            yakala["sockets"] = sockets
            self.started = True
            time.sleep(0.4)  # izleyici iş parçacığına zaman tanır
            yakala["var_mi"] = (ortam.tmp / "oturum.json").exists()

    monkeypatch.setattr(baslat, "create_app", create_app)
    monkeypatch.setattr(
        baslat,
        "uvicorn",
        SimpleNamespace(Config=lambda app, **k: SimpleNamespace(app=app, **k), Server=Server),
    )
    return ff, fp


def test_ffmpeg_yolu_ayara_yazilir_ve_oturum_json(ortam, monkeypatch, capsys):
    yakala = {}
    ff, fp = _sahte_sunucu(monkeypatch, ortam, yakala)
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    assert baslat.main([]) == 0
    assert yakala["settings"].ffmpeg_bin == str(ff)
    assert yakala["settings"].ffprobe_bin == str(fp)
    assert yakala["env_path"] == ortam.tmp / ".env"
    oturum = yakala["oturum"]
    assert yakala["var_mi"] is True
    assert ortam.acilan == [baslat.app_url(oturum.port, oturum.token)]
    assert not (ortam.tmp / "oturum.json").exists()  # çıkışta silinir
    out = capsys.readouterr().out
    assert oturum.token not in out and "127.0.0.1" not in out
    assert "Bu pencereyi kapatınca uygulama durur" in out


def test_verilmis_ffmpeg_ayari_ezilmez(ortam, monkeypatch):
    yakala = {}
    _sahte_sunucu(monkeypatch, ortam, yakala)
    ortam.settings.ffmpeg_bin = "C:/benim/ffmpeg.exe"
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    baslat.main(["--tarayici-yok"])
    assert yakala["settings"].ffmpeg_bin == "C:/benim/ffmpeg.exe"
    assert yakala["settings"].ffprobe_bin.endswith("ffprobe.exe")


@pytest.mark.parametrize("ad", ["baslat.cmd", "dagitim/uv-indir.ps1"])
def test_baslat_cmd_crlf_ve_ascii(ad):
    data = (REPO / ad).read_bytes()
    data.decode("ascii")
    assert data.endswith(b"\r\n")
    assert data.count(b"\n") == data.count(b"\r\n")


def _kilidi_tut(tmp):
    fd = baslat.acquire_lock(tmp / "baslat.lock")
    assert fd is not None
    return fd


def test_kilit_tutuluyken_bekler_ve_canli_ornegi_acar(ortam, monkeypatch):
    monkeypatch.setattr(baslat, "BEKLEME_ARALIGI_S", 0.01)
    baslat.write_instance(ortam.tmp / "oturum.json", 8123, TOKEN)
    cagri = {"n": 0}

    def alive(port, token):
        cagri["n"] += 1
        return cagri["n"] > 3

    monkeypatch.setattr(baslat, "instance_alive", alive)
    _ffmpeg_yasak(monkeypatch)
    monkeypatch.setattr(baslat, "uvicorn", SimpleNamespace(Config=_Yasak, Server=_Yasak))
    fd = _kilidi_tut(ortam.tmp)
    try:
        assert baslat.main([]) == 0
    finally:
        baslat.release_lock(fd)
    assert ortam.acilan == [baslat.app_url(8123, TOKEN)]


def test_kilit_tutuluyken_zaman_asimi(ortam, monkeypatch, capsys):
    monkeypatch.setattr(baslat, "BEKLEME_ARALIGI_S", 0.01)
    monkeypatch.setattr(baslat, "BEKLEME_ZAMAN_ASIMI_S", 0.05)
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    _ffmpeg_yasak(monkeypatch)
    fd = _kilidi_tut(ortam.tmp)
    try:
        assert baslat.main([]) == 1
    finally:
        baslat.release_lock(fd)
    out = capsys.readouterr()
    assert "zaten açılıyor" in out.out and "Traceback" not in out.out + out.err
    assert ortam.acilan == []


def test_kilit_main_sonrasi_serbest(ortam, monkeypatch):
    _sahte_sunucu(monkeypatch, ortam, {})
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    assert baslat.main(["--tarayici-yok"]) == 0
    fd = baslat.acquire_lock(ortam.tmp / "baslat.lock")
    assert fd is not None
    baslat.release_lock(fd)


def test_bekleyen_acilis_kilit_birakilinca_1_doner(ortam, monkeypatch, capsys):
    import threading

    monkeypatch.setattr(baslat, "BEKLEME_ARALIGI_S", 0.01)
    monkeypatch.setattr(baslat, "BEKLEME_ZAMAN_ASIMI_S", 30.0)
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    _ffmpeg_yasak(monkeypatch)
    monkeypatch.setattr(baslat, "uvicorn", SimpleNamespace(Config=_Yasak, Server=_Yasak))
    fd = _kilidi_tut(ortam.tmp)
    threading.Timer(0.1, baslat.release_lock, args=(fd,)).start()
    assert baslat.main([]) == 1
    out = capsys.readouterr().out
    assert "Diğer açılış durdu. baslat.cmd'yi yeniden çalıştırın." in out
    assert ortam.acilan == []
    # bekleyen aldığı kilidi geri bırakmış olmalı
    fd2 = baslat.acquire_lock(ortam.tmp / "baslat.lock")
    assert fd2 is not None
    baslat.release_lock(fd2)


def test_tarayici_acilmazsa_mesaj(ortam, monkeypatch, capsys):
    _sahte_sunucu(monkeypatch, ortam, {})
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    monkeypatch.setattr(baslat.webbrowser, "open", lambda url, *a, **k: False)
    assert baslat.main([]) == 0
    out = capsys.readouterr().out
    assert "Tarayıcı açılmadıysa baslat.cmd'ye yeniden çift tıklayın." in out


def test_tarayici_istisnasi_sessiz_olmez(ortam, monkeypatch, capsys, caplog):
    yakala = {}
    _sahte_sunucu(monkeypatch, ortam, yakala)
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)

    def boz(url, *a, **k):
        raise RuntimeError("tarayici yok")

    monkeypatch.setattr(baslat.webbrowser, "open", boz)
    assert baslat.main([]) == 0
    out = capsys.readouterr().out
    assert "Tarayıcı açılmadıysa baslat.cmd'ye yeniden çift tıklayın." in out
    oturum = yakala["oturum"]
    assert oturum.token not in out + caplog.text
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_baslat_cmd_sistem_sertifikalari():
    metin = (REPO / "baslat.cmd").read_text(encoding="ascii")
    assert 'set "UV_SYSTEM_CERTS=1"' in metin
    assert "UV_NATIVE_TLS" not in metin


def test_httpx_istek_adresleri_konsola_dusmez(ortam, monkeypatch):
    import logging

    monkeypatch.setattr(baslat, "_calistir", lambda tarayici_yok: 0)
    for ad in ("httpx", "httpcore"):
        monkeypatch.setattr(logging.getLogger(ad), "level", logging.NOTSET)
    assert baslat.main(["--tarayici-yok"]) == 0
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING


def test_instapuller_kurulamazsa_acilis_surer(ortam, monkeypatch):
    yakala = {}
    _sahte_sunucu(monkeypatch, ortam, yakala)
    monkeypatch.setattr(baslat, "ensure_instapuller", lambda root, **k: False)
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    assert baslat.main(["--tarayici-yok"]) == 0
    assert yakala["var_mi"] is True


def test_baslat_ag_yok(ortam, monkeypatch):
    import httpx

    def yasak(*a, **k):
        pytest.fail("başlatıcı testi ağa istek attı")

    monkeypatch.setattr(httpx.Client, "send", yasak)
    _sahte_sunucu(monkeypatch, ortam, {})
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    assert baslat.main(["--tarayici-yok"]) == 0


def test_js_ortami_kurulamazsa_acilis_surer(ortam, monkeypatch):
    yakala = {}
    _sahte_sunucu(monkeypatch, ortam, yakala)
    cagrildi = []
    monkeypatch.setattr(baslat, "ensure_js_ortami", lambda root, **k: cagrildi.append(root))
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    assert baslat.main(["--tarayici-yok"]) == 0
    assert cagrildi == [ortam.tmp]
    assert yakala["var_mi"] is True


def test_js_ortami_instapuller_sonrasi_cagrilir(ortam, monkeypatch):
    sira = []
    _sahte_sunucu(monkeypatch, ortam, {})
    monkeypatch.setattr(baslat, "ensure_instapuller", lambda root, **k: sira.append("ip") or True)
    monkeypatch.setattr(baslat, "ensure_js_ortami", lambda root, **k: sira.append("js"))
    monkeypatch.setattr(baslat, "instance_alive", lambda port, token: False)
    assert baslat.main(["--tarayici-yok"]) == 0
    assert sira == ["ip", "js"]
