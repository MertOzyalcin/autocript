from autocript.config import _default_tool


def test_ffmpeg_proje_icinden_bulunur(tmp_path):
    assert _default_tool(tmp_path, "ffmpeg.exe") == "ffmpeg"
    exe = tmp_path / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert _default_tool(tmp_path, "ffmpeg.exe") == str(exe)
    assert _default_tool(tmp_path, "ffprobe.exe") == "ffprobe"


# --- Instagram linki (İL §6.2, Task A1) ---
from pathlib import Path

from autocript.config import ROOT, Settings, load_settings


def test_ffprobe_yolu_fixture(ffprobe_yolu):
    assert ffprobe_yolu != "ffprobe"
    assert Path(ffprobe_yolu).is_file()
    assert Settings().ffprobe_bin == "ffprobe"


def test_conftest_gercek_arac_yasak():
    s = load_settings(env_file=None)
    assert not Path(s.instapuller_python).exists()
    assert not Path(s.instapuller_src).exists()
    assert not Path(s.js_runtime_bin).exists()


def test_instapuller_varsayilanlari(monkeypatch):
    # autouse koruma bu değişkenleri koymuştur (Argon 008)
    monkeypatch.delenv("INSTAPULLER_PYTHON")
    monkeypatch.delenv("INSTAPULLER_SRC")
    monkeypatch.delenv("INSTAPULLER_STATE_DIR")
    monkeypatch.delenv("JS_RUNTIME_BIN")
    for k in ("MAX_LINK_MB",
              "INSTAGRAM_TIMEOUT_S", "LINK_TIMEOUT_S", "MAX_DURATION_S"):
        monkeypatch.delenv(k, raising=False)
    s = load_settings(env_file=None)
    assert s.instapuller_python.endswith(r"tools\instapuller\venv\Scripts\python.exe")
    assert s.instapuller_src.endswith(r"tools\instapuller\instapuller-0.3.0")
    assert Path(s.instapuller_python).is_absolute()
    assert Path(s.instapuller_src).is_absolute()
    assert s.max_link_mb == 200
    assert s.max_duration_s == 185.0
    assert s.instapuller_state_dir == ROOT / "data" / "state"
    assert s.js_runtime_bin == str(ROOT / "tools" / "js" / "qjs.exe")
    assert s.link_timeout_s == 180.0


def test_link_ayarlari_env(monkeypatch, tmp_path):
    # Task 7: site başına durum klasörü, JS ortamı yolu, link zaman aşımı (eski ad da okunur).
    monkeypatch.setenv("INSTAPULLER_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("JS_RUNTIME_BIN", "tools/js/deno.exe")
    monkeypatch.delenv("LINK_TIMEOUT_S", raising=False)
    monkeypatch.setenv("INSTAGRAM_TIMEOUT_S", "7")
    s = load_settings(env_file=None)
    assert s.instapuller_state_dir == tmp_path
    assert s.js_runtime_bin == str(ROOT / "tools" / "js" / "deno.exe")
    assert s.link_timeout_s == 7.0
    monkeypatch.setenv("LINK_TIMEOUT_S", "9")
    assert load_settings(env_file=None).link_timeout_s == 9.0


def test_instapuller_env_ezer(monkeypatch, tmp_path):
    monkeypatch.setenv("INSTAPULLER_PYTHON", r"C:\sahte\yol\python.exe")
    monkeypatch.setenv("MAX_LINK_MB", "50")
    monkeypatch.setenv("INSTAGRAM_TIMEOUT_S", "5")
    s = load_settings(env_file=None)
    assert s.instapuller_python == r"C:\sahte\yol\python.exe"
    assert (s.max_link_mb, s.link_timeout_s) == (50, 5.0)


def test_instapuller_goreli_yol_koke_baglanir(monkeypatch):
    monkeypatch.setenv("INSTAPULLER_SRC", "tools/baska")
    assert load_settings(env_file=None).instapuller_src == str(ROOT / "tools" / "baska")


def test_tek_parcali_goreli_yollar_koke_baglanir(monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", "medya")
    monkeypatch.setenv("INSTAPULLER_SRC", "./sahte_src")
    monkeypatch.setenv("FFMPEG_BIN", "ffmpeg")
    s = load_settings(env_file=None)
    assert s.media_dir == ROOT / "medya"
    assert s.instapuller_src == str(ROOT / "sahte_src")
    assert s.ffmpeg_bin == "ffmpeg"


# --- KT2 Task 2: Gemini ve YouTube Data API temizliği ---
def test_eski_env_satirlari_yok_sayilir(tmp_path):
    import dataclasses

    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=g\nYOUTUBE_API_KEY=y\nGEMINI_MODELS=a\n", encoding="utf-8")
    s = load_settings(env_file=env)
    adlar = {f.name for f in dataclasses.fields(s)}
    assert not any("gemini" in a or "youtube" in a for a in adlar)


def test_urun_google_icermez():
    import tomllib

    veri = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for dep in veri["project"]["dependencies"]:
        assert not dep.lower().startswith("google"), dep
