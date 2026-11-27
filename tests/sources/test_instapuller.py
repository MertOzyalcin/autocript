"""InstapullerSource: gerçek alt süreç + sahte instapuller (İL §6.4, §7, KT2 Task 8). Ağa çıkmaz."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from autocript.config import Settings
from autocript.sources.instapuller import InstapullerSource
from autocript.metinler import hata_metni
from autocript.sources.hatalar import FALLBACK, INSTAPULLER_KODLARI
from autocript.sources.site_sira import SiteSiralari
from autocript.types import JobRequest, SourceError

SAHTE_SRC = Path(__file__).resolve().parent.parent / "fixtures" / "sahte_instapuller"
URL = "https://www.instagram.com/reel/ABCDE12/"
YT_ID = "abcdefghijk"
YT = f"https://www.youtube.com/watch?v={YT_ID}"


@pytest.fixture
def kur(tmp_path, monkeypatch, ffprobe_yolu, make_media):
    """kur(senaryo, **ayar) -> (kaynak, istek, kayit_yolu). Sahte videoyu da üretir."""
    kayit = tmp_path / "args.json"

    def _kur(senaryo="ok", *, audio=True, work_dir=None, siralar=None, run=subprocess.run,
             url=URL, video_codec="h264", js_var=True, **ayar):
        video = make_media("tone", 3, video_codec=video_codec, audio=audio)
        qjs = tmp_path / "qjs.exe"
        if js_var:
            qjs.write_bytes(b"")
        monkeypatch.setenv("SAHTE_IP_SENARYO", senaryo)
        monkeypatch.setenv("SAHTE_IP_VIDEO", str(video))
        monkeypatch.setenv("SAHTE_IP_ARGS", str(kayit))
        alanlar = dict(
            instapuller_python=sys.executable,
            instapuller_src=str(SAHTE_SRC),
            instapuller_state_dir=tmp_path / "state",
            js_runtime_bin=str(qjs),
            ffprobe_bin=ffprobe_yolu,
        )
        alanlar.update(ayar)
        kaynak = InstapullerSource(Settings(**alanlar), siralar or SiteSiralari(), run=run)
        wd = work_dir if work_dir is not None else tmp_path / "is"
        istek = JobRequest(job_id="j1", work_dir=wd, url=url, upload_path=None)
        return kaynak, istek, kayit

    return _kur


def _coz(kaynak, istek, asamalar=None):
    liste = asamalar if asamalar is not None else []
    return kaynak.resolve(istek, liste.append)


def _kayit(yol: Path) -> dict:
    return json.loads(yol.read_text(encoding="utf-8"))


def test_ig_basarili(kur):
    kaynak, istek, _ = kur()
    sonuc = _coz(kaynak, istek)
    assert sonuc.meta.kind == "instagram"
    assert sonuc.meta.stats["likes"] == 972107
    assert sonuc.meta.published_at.endswith("Z")
    assert sonuc.audio_path.resolve().is_relative_to(istek.work_dir.resolve())
    assert sonuc.audio_path.is_file()
    assert sonuc.transcript is None


def test_ig_argumanlari(kur):
    kaynak, istek, kayit = kur()
    _coz(kaynak, istek)
    a = _kayit(kayit)["argv"]
    assert a[:3] == ["-m", "instapuller", "fetch"]
    assert a[-2:] == ["--", URL]
    assert Path(a[a.index("--state-file") + 1]).is_absolute()
    assert "--js-runtime-bin" not in a
    assert Path(a[a.index("--ffprobe-bin") + 1]).is_absolute()
    assert float(a[a.index("--max-duration") + 1]) == 185
    assert a[a.index("--max-size-mb") + 1] == "200"
    assert "--cooldown" not in a and "--keep-video" not in a


def test_ig_sinirlar_ayardan(kur):
    kaynak, istek, kayit = kur(max_duration_s=100, max_link_mb=50)
    _coz(kaynak, istek)
    a = _kayit(kayit)["argv"]
    assert float(a[a.index("--max-duration") + 1]) == 100
    assert a[a.index("--max-size-mb") + 1] == "50"


def test_ig_is_klasoru_yoksa_olusturur(kur, tmp_path):
    wd = tmp_path / "hic" / "yok" / "is"
    kaynak, istek, _ = kur(work_dir=wd)
    assert not wd.exists()
    sonuc = _coz(kaynak, istek)
    assert sonuc.audio_path.is_file()


def test_ig_ffprobe_goreli_yol_mutlak(kur, ffprobe_yolu, monkeypatch):
    # Göreli ad PATH'ten bulunur: klasörü PATH'e ekleyip yalnızca adı veririz.
    yol = Path(ffprobe_yolu).resolve()
    monkeypatch.setenv("PATH", str(yol.parent) + os.pathsep + os.environ["PATH"])
    kaynak, istek, kayit = kur(ffprobe_bin=yol.name)
    _coz(kaynak, istek)
    a = _kayit(kayit)["argv"]
    assert Path(a[a.index("--ffprobe-bin") + 1]).is_absolute()


def test_ig_ortam_temiz(kur, monkeypatch):
    monkeypatch.setenv("INSTAPULLER_STATE_FILE", "x")
    monkeypatch.setenv("FFPROBE_BIN", "y")
    kaynak, istek, kayit = kur()
    _coz(kaynak, istek)
    env = _kayit(kayit)["env"]
    assert env["INSTAPULLER_STATE_FILE"] is None
    assert env["FFPROBE_BIN"] is None
    assert env["INSTAPULLER_PYTHON"] is None and env["INSTAPULLER_SRC"] is None
    assert env["PYTHONPATH"] == str(SAHTE_SRC)
    assert env["PYTHONUTF8"] == "1"


@pytest.mark.parametrize(
    "girdi",
    [
        "  https://www.instagram.com/reel/ABCDE12/?igsh=xyz",
        "https://m.instagram.com/reels/ABCDE12",
        "instagram.com/kullanici/reel/ABCDE12/",
    ],
)
def test_ig_kanonik_adres_gider(kur, girdi):
    kaynak, istek, kayit = kur()
    istek.url = girdi
    _coz(kaynak, istek)
    assert _kayit(kayit)["argv"][-1] == URL


@pytest.mark.parametrize("kod", sorted(INSTAPULLER_KODLARI))
def test_ig_hata_kodlari(kur, kod):
    kaynak, istek, _ = kur(f"hata:{kod}")
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    beklenen = INSTAPULLER_KODLARI[kod]
    assert e.value.code == beklenen
    assert e.value.message == hata_metni(beklenen, "tr")
    assert e.value.upload_fallback == FALLBACK[beklenen]
    assert "SAHTE MESAJ" not in str(e.value).replace(f"sahte detail {kod}", "")
    assert f"sahte detail {kod}" in e.value.detail


@pytest.mark.parametrize("senaryo", ["bozuk_json", "bos", "rc2", "rc130"])
def test_ig_beklenmeyen_ciktilar(kur, senaryo):
    kaynak, istek, _ = kur(senaryo)
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "BEKLENMEYEN_HATA"


def test_ig_zaman_asimi(kur):
    kaynak, istek, _ = kur("uyu", link_timeout_s=1)
    t0 = time.monotonic()
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "KAYNAK_GECICI"
    assert time.monotonic() - t0 < 5


def test_ig_arac_yok_python_yolu(kur, tmp_path):
    kaynak, istek, _ = kur(instapuller_python=str(tmp_path / "yok" / "python.exe"))
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "IG_ARAC_YOK"


def test_ig_arac_yok_bos_kaynak(kur, tmp_path):
    bos = tmp_path / "bos_src"
    bos.mkdir()
    kaynak, istek, _ = kur(instapuller_src=str(bos))
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "IG_ARAC_YOK"


def test_ig_ffprobe_yok(kur):
    cagrilar = []

    def run(*a, **k):
        cagrilar.append(a)
        raise AssertionError("run çağrılmamalı")

    kaynak, istek, _ = kur(ffprobe_bin="yok-boyle-bir-ffprobe", run=run)
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "FFPROBE_YOK"
    assert cagrilar == []


def test_ig_disari_yol(kur):
    kaynak, istek, _ = kur("disari_yol")
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "BEKLENMEYEN_HATA"


def test_ig_ses_yok(kur):
    kaynak, istek, _ = kur(audio=False)
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "DOSYA_SES_YOK"


def test_ig_video_uzun_derinlemesine_savunma(kur):
    kaynak, istek, _ = kur(max_duration_s=1.0)
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "VIDEO_UZUN"


def test_ig_stderr_gurultusu(kur, caplog):
    caplog.set_level(logging.INFO)
    kaynak, istek, _ = kur("stderr_gurultu")
    sonuc = _coz(kaynak, istek)
    assert sonuc.meta.kind == "instagram"
    assert "UYARI satir 49" in caplog.text


def test_ig_arac_guncel_degil_gunluk(kur, caplog):
    caplog.set_level(logging.WARNING)
    kaynak, istek, _ = kur("hata:IG_ARAC_GUNCEL_DEGIL")
    with pytest.raises(SourceError):
        _coz(kaynak, istek)
    assert any(
        r.levelno == logging.WARNING and "yt-dlp güncellenmeli" in r.getMessage() for r in caplog.records
    )


def test_ig_turkce_bosluklu_yol(kur, tmp_path):
    kaynak, istek, _ = kur(work_dir=tmp_path / "iş klasörü ĞÜŞ")
    sonuc = _coz(kaynak, istek)
    assert sonuc.meta.title == "Türkçe başlık: ğüşiöç İĞÜŞÖÇ"


def test_ig_on_stage_sirasi(kur):
    # Sırasız ilk çağrı: yalnızca "kaynak".
    siralar = SiteSiralari(clock=lambda: 0.0, sleep=lambda s: None)
    kaynak, istek, _ = kur(siralar=siralar)
    a1: list[str] = []
    _coz(kaynak, istek, a1)
    assert a1 == ["kaynak"]
    # İkinci çağrı: önceki bitiş 0.0, saat hâlâ 0.0 -> bekleme gerekir: "sira" sonra "kaynak".
    a2: list[str] = []
    _coz(kaynak, istek, a2)
    assert a2 == ["sira", "kaynak"]


def test_ig_goreli_work_dir_ve_src_mutlak_gider(kur, tmp_path, monkeypatch):
    import shutil

    src_kopya = tmp_path / "sahte_src"
    shutil.copytree(SAHTE_SRC, src_kopya)
    monkeypatch.chdir(tmp_path)
    kaynak, istek, kayit = kur(work_dir=Path("goreli_is"), instapuller_src="sahte_src")
    sonuc = _coz(kaynak, istek)
    assert sonuc.audio_path.is_file()
    k = _kayit(kayit)
    assert Path(k["env"]["PYTHONPATH"]).is_absolute()
    assert Path(k["argv"][k["argv"].index("--out-dir") + 1]).is_absolute()


def test_ig_meta_duration_null_ve_yuvarlama(kur, monkeypatch):
    monkeypatch.setenv("SAHTE_IP_DURATION", "null")
    kaynak, istek, _ = kur()
    s1 = _coz(kaynak, istek)
    assert isinstance(s1.meta.duration_s, float) and 2.5 <= s1.meta.duration_s <= 3.5

    monkeypatch.setenv("SAHTE_IP_DURATION", "2.3456")
    kaynak2, istek2, _ = kur()
    s2 = _coz(kaynak2, istek2)
    assert s2.meta.duration_s == 2.35


# --- KT2 Task 8: YouTube, site başına sıra ve durum dosyası ---


class _KayitliRun:
    """subprocess.run sarmalayıcı: her çağrının argümanlarını tutar."""

    def __init__(self):
        self.cagrilar: list[list[str]] = []

    def __call__(self, args, **kw):
        self.cagrilar.append(list(args))
        return subprocess.run(args, **kw)


class _Saat:
    def __init__(self):
        self.t = 100.0
        self.uykular: list[float] = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.uykular.append(s)
        self.t += s


def test_kanonik_youtube_adresi_gider(kur):
    for girdi in (
        f"https://www.youtube.com/shorts/{YT_ID}?feature=share",
        f"https://youtu.be/{YT_ID}?si=x",
        f"https://m.youtube.com/watch?v={YT_ID}&t=1",
    ):
        kaynak, istek, kayit = kur(url=girdi, video_codec=None)
        sonuc = _coz(kaynak, istek)
        assert _kayit(kayit)["argv"][-1] == YT
        assert sonuc.meta.kind == "youtube"
        assert sonuc.meta.platform_id == YT_ID
        assert sonuc.meta.url == YT
        assert sonuc.audio_path.suffix == ".m4a"


def test_site_basina_durum_dosyasi(kur, tmp_path):
    run = _KayitliRun()
    kaynak, istek, _ = kur(run=run, siralar=SiteSiralari(clock=lambda: 0.0, sleep=lambda s: None))
    _coz(kaynak, istek)
    yt_istek = JobRequest(job_id="j2", work_dir=istek.work_dir, url=YT, upload_path=None)
    _coz(kaynak, yt_istek)
    ig_args, yt_args = run.cagrilar
    durum = tmp_path / "state"
    assert Path(ig_args[ig_args.index("--state-file") + 1]) == (durum / "instapuller-instagram.json").resolve()
    assert Path(yt_args[yt_args.index("--state-file") + 1]) == (durum / "instapuller-youtube.json").resolve()


def test_siteler_birbirini_beklemez(kur):
    saat = _Saat()
    kaynak, istek, _ = kur(siralar=SiteSiralari(clock=saat.clock, sleep=saat.sleep), video_codec=None)
    a1: list[str] = []
    _coz(kaynak, istek, a1)
    assert a1 == ["kaynak"]
    yt_istek = JobRequest(job_id="j2", work_dir=istek.work_dir, url=YT, upload_path=None)
    a2: list[str] = []
    _coz(kaynak, yt_istek, a2)
    assert a2 == ["kaynak"]  # "sira" yok
    assert saat.uykular == []


def test_ayni_site_15sn(kur):
    saat = _Saat()
    kaynak, istek, _ = kur(url=YT, siralar=SiteSiralari(clock=saat.clock, sleep=saat.sleep), video_codec=None)
    _coz(kaynak, istek)
    assert saat.uykular == []
    a2: list[str] = []
    _coz(kaynak, istek, a2)
    assert saat.uykular == [15.0]
    assert a2 == ["sira", "kaynak"]


def test_js_arg_yalnizca_youtube(kur, tmp_path):
    run = _KayitliRun()
    kaynak, istek, _ = kur(run=run, siralar=SiteSiralari(clock=lambda: 0.0, sleep=lambda s: None), video_codec=None)
    _coz(kaynak, istek)
    _coz(kaynak, JobRequest(job_id="j2", work_dir=istek.work_dir, url=YT, upload_path=None))
    ig_args, yt_args = run.cagrilar
    assert "--js-runtime-bin" not in ig_args
    yol = yt_args[yt_args.index("--js-runtime-bin") + 1]
    assert Path(yol).is_absolute()
    assert Path(yol) == (tmp_path / "qjs.exe").resolve()
    assert yt_args[-2:] == ["--", YT]


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_js_ortami_yoksa_instapuller_cagrilmaz(kur, dil):
    run = _KayitliRun()
    saat = _Saat()
    kaynak, istek, _ = kur(
        url=YT, run=run, js_var=False, video_codec=None,
        siralar=SiteSiralari(clock=saat.clock, sleep=saat.sleep),
    )
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "JS_ORTAMI_YOK"
    assert e.value.upload_fallback is True
    assert e.value.params == {"site": "youtube"}
    assert "YouTube" in hata_metni("JS_ORTAMI_YOK", dil, e.value.params)
    assert run.cagrilar == []
    assert saat.uykular == []
    # Sıra alınmadı: hemen ardından Instagram işi bekleme olmadan normal biter.
    ig_istek = JobRequest(job_id="j2", work_dir=istek.work_dir, url=URL, upload_path=None)
    a: list[str] = []
    assert _coz(kaynak, ig_istek, a).meta.kind == "instagram"
    assert a == ["kaynak"]


def test_js_ortami_yok_sira_harcamaz(kur):
    saat = _Saat()
    kaynak, istek, _ = kur(
        url=YT, js_var=False, video_codec=None, siralar=SiteSiralari(clock=saat.clock, sleep=saat.sleep)
    )
    with pytest.raises(SourceError):
        _coz(kaynak, istek)
    # Sıra kullanılmadığı için ikinci deneme de beklemeden aynı hatayı verir.
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "JS_ORTAMI_YOK"
    assert saat.uykular == []


def test_instapuller_js_ortami_yok_kodu_eslenir(kur):
    kaynak, istek, _ = kur("hata:JS_ORTAMI_YOK", url=YT, video_codec=None)
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "JS_ORTAMI_YOK"
    assert e.value.params == {"site": "youtube"}


def test_beklenmeyen_meta_kind(kur, monkeypatch):
    kaynak, istek, _ = kur(url=YT, video_codec=None)
    monkeypatch.setenv("SAHTE_IP_KIND", "instagram")
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.code == "BEKLENMEYEN_HATA"


def test_hatalar_site_tasir(kur):
    kaynak, istek, _ = kur("hata:IG_ERISILEMEDI", url=YT, video_codec=None)
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.params == {"site": "youtube"}
    assert "YouTube" in e.value.message
    kaynak, istek, _ = kur("hata:IG_ERISILEMEDI")
    with pytest.raises(SourceError) as e:
        _coz(kaynak, istek)
    assert e.value.params == {"site": "instagram"}


def test_dash_uyarisi_gunluge(kur, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv(
        "SAHTE_IP_STDERR", "WARNING: [youtube] writing DASH m4a. Only some players support this container"
    )
    kaynak, istek, _ = kur(url=YT, video_codec=None)
    sonuc = _coz(kaynak, istek)
    assert sonuc.meta.kind == "youtube"
    assert "writing DASH m4a" in caplog.text
