"""SiteSirasi: tek kilit ve bitişten itibaren 15 sn aralık (İL §6.3)."""

from __future__ import annotations

import threading

import pytest

from autocript.sources.site_sira import SiteSirasi


class SahteSaat:
    def __init__(self) -> None:
        self.t = 1000.0
        self.uykular: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.uykular.append(s)
        self.t += s


def _kur():
    saat = SahteSaat()
    return saat, SiteSirasi(clock=saat.clock, sleep=saat.sleep)


def test_bekleme_sabit():
    assert SiteSirasi.BEKLEME_S == 15.0


def test_ilk_cagri_beklemez():
    saat, sira = _kur()
    bekle = []
    assert sira.calistir(lambda: "ok", lambda: bekle.append(1)) == "ok"
    assert saat.uykular == []
    assert bekle == []


def test_ikinci_cagri_bitisten_15sn_bekler():
    saat, sira = _kur()
    sira.calistir(lambda: saat.sleep(4.0), lambda: None)
    saat.uykular.clear()
    bekle = []
    sira.calistir(lambda: None, lambda: bekle.append(1))
    assert saat.uykular == [15.0]
    assert bekle == [1]


def test_hata_da_zamani_yazar():
    saat, sira = _kur()

    def hata():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        sira.calistir(hata, lambda: None)
    bekle = []
    sira.calistir(lambda: None, lambda: bekle.append(1))
    assert saat.uykular == [15.0]
    assert bekle == [1]


def test_sure_dolduysa_beklemez():
    saat, sira = _kur()
    sira.calistir(lambda: None, lambda: None)
    saat.t += 20.0
    bekle = []
    sira.calistir(lambda: None, lambda: bekle.append(1))
    assert saat.uykular == []
    assert bekle == []


def test_kilit_doluyken_on_wait():
    saat, sira = _kur()
    birinci_basladi = threading.Event()
    birakma = threading.Event()
    ikinci_on_wait = threading.Event()
    sayac = {"aktif": 0, "en_fazla": 0}
    olaylar: list[str] = []
    lk = threading.Lock()

    def fn(ad, bekle=None):
        def i():
            with lk:
                sayac["aktif"] += 1
                sayac["en_fazla"] = max(sayac["en_fazla"], sayac["aktif"])
                olaylar.append(f"{ad}-basla")
            birinci_basladi.set()
            if bekle is not None:
                assert bekle.wait(5)
            with lk:
                sayac["aktif"] -= 1

        return i

    def on_wait():
        olaylar.append("on_wait")
        ikinci_on_wait.set()

    t1 = threading.Thread(target=lambda: sira.calistir(fn("1", birakma), lambda: None))
    t2 = threading.Thread(target=lambda: sira.calistir(fn("2"), on_wait))
    t1.start()
    assert birinci_basladi.wait(5)
    t2.start()
    assert ikinci_on_wait.wait(5)
    assert "2-basla" not in olaylar
    birakma.set()
    t1.join(5)
    t2.join(5)
    assert not t1.is_alive() and not t2.is_alive()
    assert olaylar.index("on_wait") < olaylar.index("2-basla")
    assert sayac["en_fazla"] == 1


def test_kilit_dolu_ve_sure_dolmamis_on_wait_bir_kez():
    saat, sira = _kur()
    sira.calistir(lambda: None, lambda: None)  # son_bitis yazılır, 15 sn dolmadı
    basladi = threading.Event()
    birak = threading.Event()
    ikinci_bildirdi = threading.Event()
    sayac = []

    def uzun():
        basladi.set()
        assert birak.wait(5)

    t1 = threading.Thread(target=lambda: sira.calistir(uzun, lambda: None))
    t1.start()
    assert basladi.wait(5)

    def on_wait():
        sayac.append(1)
        ikinci_bildirdi.set()

    t2 = threading.Thread(target=lambda: sira.calistir(lambda: None, on_wait))
    t2.start()
    assert ikinci_bildirdi.wait(5)
    birak.set()
    t1.join(5)
    t2.join(5)
    assert not t1.is_alive() and not t2.is_alive()
    assert sayac == [1]


def test_es_zamanli_iki_cagri_tam_biri_on_wait_alir():
    saat, sira = _kur()
    bariyer = threading.Barrier(2, timeout=5)
    bildirim = threading.Event()
    kilit = threading.Lock()
    durum = {"aktif": 0, "en_fazla": 0}
    on_waitler: list[int] = []

    def fn():
        with kilit:
            durum["aktif"] += 1
            durum["en_fazla"] = max(durum["en_fazla"], durum["aktif"])
        # ilk giren, ikincinin on_wait'i görene kadar tutar
        assert bildirim.wait(5)
        with kilit:
            durum["aktif"] -= 1

    def on_wait():
        on_waitler.append(1)
        bildirim.set()

    def is_():
        bariyer.wait()
        sira.calistir(fn, on_wait)

    ts = [threading.Thread(target=is_) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert not any(t.is_alive() for t in ts)
    assert on_waitler == [1]
    assert durum["en_fazla"] == 1


def test_on_wait_hata_verirse_kilit_serbest_kalir():
    saat, sira = _kur()
    sira.calistir(lambda: None, lambda: None)  # sonraki çağrı beklemeli

    def kotu():
        raise RuntimeError("on_wait")

    with pytest.raises(RuntimeError):
        sira.calistir(lambda: None, kotu)
    # kilit tutulmuyor: yeni çağrı takılmadan döner
    sonuc = []
    t = threading.Thread(target=lambda: sonuc.append(sira.calistir(lambda: 7, lambda: None)))
    t.start()
    t.join(5)
    assert not t.is_alive()
    assert sonuc == [7]


# --- SiteSiralari: site başına bir sıra (KT2 Task 8) ---


def test_siralar_site_basina_tek_ornek():
    from autocript.sources.site_sira import SiteSiralari

    siralar = SiteSiralari()
    assert siralar.sira("youtube") is siralar.sira("youtube")
    assert siralar.sira("youtube") is not siralar.sira("instagram")
    assert isinstance(siralar.sira("instagram"), SiteSirasi)


def test_siralar_saat_paylasilir():
    from autocript.sources.site_sira import SiteSiralari

    saat = SahteSaat()
    siralar = SiteSiralari(clock=saat.clock, sleep=saat.sleep)
    siralar.sira("instagram").calistir(lambda: None, lambda: None)
    siralar.sira("youtube").calistir(lambda: None, lambda: None)
    assert saat.uykular == []
    siralar.sira("youtube").calistir(lambda: None, lambda: None)
    assert saat.uykular == [15.0]


def test_siralar_es_zamanli_tek_ornek():
    from autocript.sources.site_sira import SiteSiralari

    siralar = SiteSiralari()
    bulunan = []
    ts = [threading.Thread(target=lambda: bulunan.append(siralar.sira("youtube"))) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len({id(b) for b in bulunan}) == 1
