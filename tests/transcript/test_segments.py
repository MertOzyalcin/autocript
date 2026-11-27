import json
from pathlib import Path

from autocript.transcript.segments import group_minutes, split_segments
from autocript.types import NonSpeech, RawWord


def w(text, s, e):
    return RawWord(text, s, e, 0.9)


def test_noktalama_boler():
    assert split_segments([w("Merhaba.", 0, 0.5), w("dünya", 0.6, 1.0)], []) == [(0, 1), (1, 2)]


def test_bosluk_siniri():
    assert split_segments([w("a", 0, 0.5), w("b", 1.3, 1.5)], []) == [(0, 1), (1, 2)]
    assert split_segments([w("a", 0, 0.5), w("b", 1.1, 1.5)], []) == [(0, 2)]


def test_uzunluk_ve_sure():
    words = [w("kelime", i * 0.3, i * 0.3 + 0.25) for i in range(20)]
    for a, b in split_segments(words, []):
        assert len(" ".join(x.text for x in words[a:b])) <= 84
    slow = [w("a", i * 0.6, i * 0.6 + 0.5) for i in range(20)]
    for a, b in split_segments(slow, []):
        assert slow[b - 1].end - slow[a].start <= 7


def test_konusmasiz_aralik():
    words = [w("a", 0, 0.5), w("b", 0.6, 1.0), w("c", 2.0, 2.3)]
    assert split_segments(words, [NonSpeech(1.2, 1.9, "music")]) == [(0, 2), (2, 3)]


def test_bos():
    assert split_segments([], []) == []


def test_bolme_tam_0_7_bosluk_bolmez():
    assert split_segments([w("a", 0.0, 0.6), w("b", 1.3, 1.5)], []) == [(0, 2)]


def test_bolme_tam_7_sn_bolmez():
    # 8.05 - 1.05 kayan noktada 7.000000000000001 olur; tam 7 sn bölmemeli
    words = [w("a", round(1.05 + 0.5 * i, 2), round(1.45 + 0.5 * i, 2)) for i in range(13)]
    words.append(w("b", 7.55, 8.05))
    assert split_segments(words, []) == [(0, len(words))]


def test_group_minutes_bos_dakika():
    segs = [{"start": 5.0, "end": 6.0, "text": "a", "word_range": [0, 1]}]
    m = group_minutes(segs, 130.0)
    assert [x["segment_range"] for x in m] == [[0, 1], [1, 1], [1, 1]]
    assert m[2]["end"] == 130.0 and m[1]["text"] == ""


# --- İngilizce kısaltmalar (KT2 Task 4) ---

FIKSTUR = Path(__file__).resolve().parents[1] / "fixtures" / "ingilizce_kelimeler.json"
BEKLENEN_CUMLELER = [
    "Hi, I'm Dr. Smith.",
    "Today we test the U.S. version, e.g. the new one.",
    "Is it fast?",
    "Yes!",
    "It costs 3.5 dollars...",
    "Thanks, Mr. Lee.",
]


def ingilizce_kelimeler():
    ham = json.loads(FIKSTUR.read_text(encoding="utf-8"))
    return [RawWord(x["text"], x["start"], x["end"], x["confidence"]) for x in ham]


def test_ingilizce_cumleler():
    words = ingilizce_kelimeler()
    ranges = split_segments(words, [])
    assert [" ".join(x.text for x in words[a:b]) for a, b in ranges] == BEKLENEN_CUMLELER


def test_kisaltma_tirnak_parantez():
    for ilk in ("(e.g.", '"Dr.', "“Mr.", "Dr.)", "(U.S.)"):
        words = [w(ilk, 0, 0.3), w("Smith", 0.4, 0.7)]
        assert split_segments(words, []) == [(0, 2)], ilk
    # Kısaltma olmayan nokta hâlâ böler.
    assert split_segments([w("Done.", 0, 0.3), w("Next", 0.4, 0.7)], []) == [(0, 1), (1, 2)]


def test_kisaltma_turkce_metinde_de_gecerli():
    words = [w("Dr.", 0, 0.3), w("Ayşe", 0.4, 0.7), w("geldi.", 0.8, 1.0), w("Sonra", 1.1, 1.4)]
    assert split_segments(words, []) == [(0, 3), (3, 4)]
