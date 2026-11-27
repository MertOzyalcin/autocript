"""Site başına indirme kilidi ve 15 sn aralığı (İL §6.3, KT2 kararı 2).

Bir sitenin tüm indirmeleri süreç genelinde kendi sırasından geçer; siteler birbirini beklemez. İş hattı iş parçacıklarında
çalıştığı için asyncio değil `threading.Lock` kullanılır. Süre, bir önceki çağrının
BİTİŞİNDEN ölçülür; başarı da hata da bitiş sayılır. Son bitiş zamanı yalnızca bellekte durur.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class SiteSirasi:
    # Sabit değer: ayardan gelmez, 15'in altına indirilemez.
    BEKLEME_S = 15.0

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._kilit = threading.Lock()
        self._son_bitis: float | None = None

    def _kalan(self) -> float:
        if self._son_bitis is None:
            return 0.0
        return self._son_bitis + self.BEKLEME_S - self._clock()

    def calistir(self, fn: Callable[[], T], on_wait: Callable[[], None]) -> T:
        # "Sırada" bilgisi çağrı başına en fazla bir kez verilir. Karar kilidin kendisinden
        # çıkar: kilit alınamazsa sırada demektir (kontrol-sonra-al yarışı yok).
        bildirildi = False
        if not self._kilit.acquire(blocking=False):
            bildirildi = True
            on_wait()  # kilit henüz tutulmuyor; burada hata çıkarsa elde bir şey kalmaz
            self._kilit.acquire()
        try:
            kalan = self._kalan()
            if kalan > 0:
                if not bildirildi:
                    on_wait()
                self._sleep(kalan)
            try:
                return fn()
            finally:
                self._son_bitis = self._clock()
        finally:
            self._kilit.release()


class SiteSiralari:
    """Site kimliğine göre tembel oluşturulan `SiteSirasi` örnekleri (kilitle korunur)."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._kilit = threading.Lock()
        self._siralar: dict[str, SiteSirasi] = {}

    def sira(self, site: str) -> SiteSirasi:
        with self._kilit:
            if site not in self._siralar:
                self._siralar[site] = SiteSirasi(clock=self._clock, sleep=self._sleep)
            return self._siralar[site]
