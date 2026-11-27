"""baslat.cmd'nin Akıllı Uygulama Denetimi (SAC) kontrolü.

baslat.cmd'nin bir kopyası gerçek cmd.exe ile çalıştırılır; yalnızca reg.exe yerine sahte bir
betik konur. dagitim/uv-indir.ps1 yerine, "kurulum başladı" izini bırakıp hata veren bir taslak
durur; böylece hiçbir test bir şey indirmez ve kayıt defterine dokunmaz.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

REG_EXE = r"%SystemRoot%\System32\reg.exe"
SORGU = (
    r"query HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy "
    "/v VerifiedAndReputablePolicyState"
)

ACIK = {"tr": "Akilli Uygulama Denetimi bu bilgisayarda acik.", "en": "Smart App Control is on for this computer."}
DEGERLENDIRME = {
    "tr": "Uyari: Akilli Uygulama Denetimi degerlendirme modunda.",
    "en": "Warning: Smart App Control is in evaluation mode.",
}
BILGI = {
    "tr": (
        "Denetim aciksa imzasiz araclari (Python, ffmpeg vb.) engeller",
        "Windows Guvenligi > Uygulama ve tarayici denetimi > Akilli Uygulama Denetimi",
        "Karar sizindir.",
    ),
    "en": (
        "When it is on, it blocks unsigned tools (Python, ffmpeg and others)",
        "Windows Security > App & browser control > Smart App Control",
        "The choice is yours.",
    ),
}
KURULUM_BASLADI = {"tr": "uv indiriliyor...", "en": "Downloading uv..."}
GENEL_HATA = ("Bir sorun oldu", "Something went wrong")


def _sahte_reg(deger: str | None) -> str:
    satirlar = ["@echo off", 'echo %*>"%~dp0reg-cagrildi.txt"']
    if deger is None:
        satirlar += [
            "echo ERROR: The system was unable to find the specified registry key or value. 1>&2",
            "exit /b 1",
        ]
    else:
        satirlar += [
            "echo.",
            r"echo HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\CI\Policy",
            f"echo     VerifiedAndReputablePolicyState    REG_DWORD    {deger}",
            "echo.",
            "exit /b 0",
        ]
    return "\r\n".join(satirlar) + "\r\n"


def _calistir(tmp: Path, dil: str, deger: str | None, *, reg_yok: bool = False, ek_env=None):
    metin = (REPO / "baslat.cmd").read_text(encoding="ascii")
    sahte = r".\sahte-yok.exe" if reg_yok else r".\sahte-reg.cmd"
    (tmp / "baslat.cmd").write_text(metin.replace(REG_EXE, sahte), encoding="ascii", newline="\r\n")
    if not reg_yok:
        (tmp / "sahte-reg.cmd").write_text(_sahte_reg(deger), encoding="ascii", newline="")
    (tmp / "dagitim").mkdir()
    (tmp / "dagitim" / "uv-indir.ps1").write_text(
        "Set-Content -Path (Join-Path $PSScriptRoot 'cagrildi.txt') -Value x\nexit 1\n",
        encoding="ascii",
    )
    env = {**os.environ, "AUTOCRIPT_KONSOL_DIL": dil, **(ek_env or {})}
    r = subprocess.run(
        ["cmd.exe", "/d", "/c", str(tmp / "baslat.cmd")],
        cwd=tmp,
        env=env,
        input=b"\r\n\r\n\r\n",
        capture_output=True,
        timeout=60,
    )
    cikti = (r.stdout + r.stderr).decode("ascii", errors="replace")
    kurulum = (tmp / "dagitim" / "cagrildi.txt").exists()
    return r.returncode, cikti, kurulum


def _sorgu_yapildi(tmp: Path) -> bool:
    iz = tmp / "reg-cagrildi.txt"
    return iz.exists() and iz.read_text(encoding="ascii").strip() == SORGU


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_sac_acik_kurulum_baslamaz(tmp_path, dil):
    kod, cikti, kurulum = _calistir(tmp_path, dil, "0x1")
    assert ACIK[dil] in cikti
    for parca in BILGI[dil]:
        assert parca in cikti
    assert kurulum is False
    assert KURULUM_BASLADI[dil] not in cikti
    assert not any(m in cikti for m in GENEL_HATA)
    assert kod == 1
    assert _sorgu_yapildi(tmp_path)


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_sac_degerlendirme_uyarir_ve_devam_eder(tmp_path, dil):
    _, cikti, kurulum = _calistir(tmp_path, dil, "0x2")
    assert DEGERLENDIRME[dil] in cikti
    for parca in BILGI[dil]:
        assert parca in cikti
    assert kurulum is True
    assert cikti.index(DEGERLENDIRME[dil]) < cikti.index(KURULUM_BASLADI[dil])
    assert _sorgu_yapildi(tmp_path)


def _sessiz_devam(cikti: str, kurulum: bool, dil: str):
    assert "Akilli Uygulama" not in cikti and "Smart App Control" not in cikti
    assert "ERROR" not in cikti and "sahte-" not in cikti
    assert KURULUM_BASLADI[dil] in cikti
    assert kurulum is True


@pytest.mark.parametrize("deger", ["0x0", None], ids=["kapali", "deger-yok"])
def test_sac_kapali_ya_da_deger_yok_sessiz_devam(tmp_path, deger):
    _, cikti, kurulum = _calistir(tmp_path, "tr", deger)
    _sessiz_devam(cikti, kurulum, "tr")
    assert _sorgu_yapildi(tmp_path)


def test_sac_okunamazsa_sessiz_devam(tmp_path):
    _, cikti, kurulum = _calistir(tmp_path, "en", None, reg_yok=True)
    _sessiz_devam(cikti, kurulum, "en")


def test_sac_disaridan_gelen_degisken_sayilmaz(tmp_path):
    _, cikti, kurulum = _calistir(tmp_path, "tr", None, ek_env={"SAC_DURUM": "0x1"})
    _sessiz_devam(cikti, kurulum, "tr")


def test_sac_gercek_anahtar_yonetici_izni_olmadan_okunur():
    metin = (REPO / "baslat.cmd").read_text(encoding="ascii")
    assert f"{REG_EXE} {SORGU}" in metin
    assert metin.index(SORGU) < metin.index("uv-indir.ps1")
    assert "runas" not in metin.lower()


def test_sac_acik_mesaji_pencereyi_acik_tutar():
    metin = (REPO / "baslat.cmd").read_text(encoding="ascii")
    blok = metin.split("\n:sac_acik\n", 1)[1].split("exit /b", 1)[0]
    assert "pause" in blok
