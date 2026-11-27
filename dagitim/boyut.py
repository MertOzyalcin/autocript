"""Kurulum boyutu ölçümü: bir klasörün üst klasörleri için bayt ve dosya sayısı.

Kullanım: python dagitim/boyut.py <klasör>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def olc(kok: Path) -> dict[str, tuple[int, int]]:
    """`kok` altındaki her üst klasör için (bayt, dosya sayısı); "TOPLAM" da eklenir.

    Sabit bağlar bir kez sayılır ((st_dev, st_ino) kümesi). Kökün doğrudan altındaki
    dosyalar "." girdisinde toplanır. Sembolik bağlar izlenmez.
    """
    kok = Path(kok)
    gorulen: set[tuple[int, int]] = set()
    sonuc: dict[str, tuple[int, int]] = {}
    toplam_bayt = 0
    toplam_dosya = 0
    for ust in sorted(kok.iterdir(), key=lambda p: p.name.lower()):
        if ust.is_dir() and not ust.is_symlink():
            dosyalar = (Path(d) / f for d, _, fs in os.walk(ust) for f in fs)
            ad = ust.name
        else:
            dosyalar = iter([ust])
            ad = "."
        bayt, adet = sonuc.get(ad, (0, 0))
        for p in dosyalar:
            try:
                st = p.lstat()
            except OSError:
                continue
            anahtar = (st.st_dev, st.st_ino)
            if st.st_ino and anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            bayt += st.st_size
            adet += 1
        sonuc[ad] = (bayt, adet)
        toplam_bayt = sum(b for b, _ in sonuc.values())
        toplam_dosya = sum(n for _, n in sonuc.values())
    sonuc["TOPLAM"] = (toplam_bayt, toplam_dosya)
    return sonuc


def tablo(sonuc: dict[str, tuple[int, int]]) -> str:
    satirlar = [f"{'klasor':<20}{'MB':>12}{'dosya':>10}"]
    for ad, (bayt, adet) in sonuc.items():
        satirlar.append(f"{ad:<20}{bayt / 1_000_000:>12.1f}{adet:>10}")
    return "\n".join(satirlar)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Kullanim: python dagitim/boyut.py <klasor>", file=sys.stderr)
        return 2
    kok = Path(argv[1])
    if not kok.is_dir():
        print(f"Klasor bulunamadi: {kok}", file=sys.stderr)
        return 1
    print(tablo(olc(kok)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
