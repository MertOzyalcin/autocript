import json
import re
from pathlib import Path

from autocript.export import to_json, to_srt, to_txt
from autocript.transcript.segments import KISALTMALAR, split_segments
from autocript.types import RawWord

CUE = re.compile(
    r"(\d+)\n(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})\n([^\n]+(?:\n[^\n]+)*)"
)


def ts(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(srt):
    cues = []
    for block in srt.strip().split("\n\n"):
        m = CUE.fullmatch(block)
        assert m, block
        n = int(m.group(1))
        start = ts(*m.group(2, 3, 4, 5))
        end = ts(*m.group(6, 7, 8, 9))
        cues.append((n, start, end, m.group(10).split("\n")))
    return cues


def doc(words, timing="word", segments=None, minutes=None):
    if segments is None:
        segments = (
            [{"start": words[0]["start"], "end": words[-1]["end"],
              "text": " ".join(x["text"] for x in words), "word_range": [0, len(words)]}]
            if words else []
        )
    if minutes is None:
        minutes = (
            [{"minute": 0, "start": 0.0, "end": 60.0,
              "text": " ".join(s["text"] for s in segments), "segment_range": [0, len(segments)]}]
            if segments else []
        )
    return {
        "schema_version": "1.0", "job_id": "j", "created_at": "2026-01-01T00:00:00Z",
        "language": "tr", "timing": timing, "words": words, "segments": segments,
        "minutes": minutes, "non_speech": [], "warnings": [],
    }


def mkwords(texts, step=0.4):
    return [
        {"i": i, "text": t, "start": round(i * step, 2), "end": round(i * step + step * 0.9, 2),
         "confidence": 0.9, "low_confidence": False}
        for i, t in enumerate(texts)
    ]


LONG = ["kelime%02d" % i for i in range(15)]  # 15 * 8 + 14 = 134 karakter


def test_stamp():
    from autocript.export.formats import stamp
    assert stamp(0.86) == "[00:00.86]"
    assert stamp(59.996) == "[01:00.00]"
    assert stamp(125.5) == "[02:05.50]"
    assert stamp(-1) == "[00:00.00]"


def test_txt_cumle_satirlari():
    d = doc([], segments=[
        {"start": 1.0, "end": 2.0, "text": "Birinci.", "word_range": [0, 0]},
        {"start": 61.0, "end": 62.0, "text": "İkinci.", "word_range": [0, 0]},
    ])
    assert to_txt(d) == "[00:01.00] Birinci.\n[01:01.00] İkinci.\n"


def test_txt_konusmasiz_satir():
    d = doc([], segments=[
        {"start": 0.5, "end": 2.0, "text": "Önce.", "word_range": [0, 0]},
        {"start": 9.0, "end": 10.0, "text": "Sonra.", "word_range": [0, 0]},
    ])
    d["non_speech"] = [{"start": 3.0, "end": 8.0, "kind": "music"}]
    assert to_txt(d).splitlines() == ["[00:00.50] Önce.", "[00:03.00] [müzik]", "[00:09.00] Sonra."]
    # aynı anda başlayan segment ve aralık: önce segment
    d["non_speech"] = [{"start": 9.0, "end": 12.0, "kind": "unknown"}]
    assert to_txt(d).splitlines()[1:] == ["[00:09.00] Sonra.", "[00:09.00] [konuşma yok]"]


def test_txt_cumle_ortasindan_bolunmez():
    d = doc([], segments=[
        {"start": 10.0, "end": 11.0, "text": "Yarın sabah erkenden", "word_range": [0, 0]},
        {"start": 11.8, "end": 13.0, "text": "yola çıkacağız.", "word_range": [0, 0]},
        {"start": 13.5, "end": 14.5, "text": "Sonraki cümle.", "word_range": [0, 0]},
    ])
    assert to_txt(d) == (
        "[00:10.00] Yarın sabah erkenden yola çıkacağız.\n"
        "[00:13.50] Sonraki cümle.\n"
    )


def test_txt_uzun_cumle_noktalamadan_bolunur():
    # İki nokta (:) ile bölünme
    p1 = ("uzun kelime " * 11).strip() + " dedi:"  # ~137 karakter
    p2 = ("devam eden sözler " * 6).strip() + " bitti."  # ~114 karakter (toplam > 200)
    d = doc([], segments=[
        {"start": 1.0, "end": 6.0, "text": p1, "word_range": [0, 0]},
        {"start": 6.5, "end": 12.0, "text": p2, "word_range": [0, 0]},
    ])
    lines = to_txt(d).splitlines()
    assert len(lines) == 2
    assert lines[0] == f"[00:01.00] {p1}"
    assert lines[1] == f"[00:06.50] {p2}"

    # Tırnak (") ile bölünme
    q1 = ("uzun kelime " * 11).strip() + ' "söz"'
    q2 = ("sonraki sözler " * 7).strip() + "."
    d2 = doc([], segments=[
        {"start": 2.0, "end": 7.0, "text": q1, "word_range": [0, 0]},
        {"start": 7.5, "end": 13.0, "text": q2, "word_range": [0, 0]},
    ])
    lines2 = to_txt(d2).splitlines()
    assert len(lines2) == 2
    assert lines2[0] == f"[00:02.00] {q1}"
    assert lines2[1] == f"[00:07.50] {q2}"

    # Hiç noktalama yoksa kelime/cümle ortasından bölünmez
    r1 = ("noktalamasiz " * 10).strip()
    r2 = ("devam " * 20).strip()
    d3 = doc([], segments=[
        {"start": 0.5, "end": 5.0, "text": r1, "word_range": [0, 0]},
        {"start": 5.5, "end": 10.0, "text": r2, "word_range": [0, 0]},
    ])
    assert len(to_txt(d3).splitlines()) == 1


def test_srt_7sn_siniri_korunur_txt_tek_satir():
    words = [
        {"i": i, "text": "kelime", "start": float(i), "end": i + 0.5, "confidence": 0.9, "low_confidence": False}
        for i in range(10)
    ]
    d = doc(words, segments=[
        {"start": 0.0, "end": 5.5, "text": " ".join("kelime" for _ in range(6)), "word_range": [0, 6]},
        {"start": 6.0, "end": 9.5, "text": " ".join("kelime" for _ in range(4)), "word_range": [6, 10]},
    ])
    # TXT tek satırda birleştirir, SRT 7 sn sınırını korur
    assert len(to_txt(d).splitlines()) == 1
    cues = parse_srt(to_srt(d))
    assert len(cues) >= 2
    _check_cues(cues)


def test_srt_bicim():
    cues = parse_srt(to_srt(doc(mkwords(LONG * 3))))
    assert [c[0] for c in cues] == list(range(1, len(cues) + 1))
    prev = 0.0
    for _, start, end, lines in cues:
        assert start >= prev and end >= start and end - start <= 7
        assert 1 <= len(lines) <= 2 and all(len(l) <= 42 for l in lines)
        prev = end


def test_srt_ortusen_kelimeler():
    # build'den geçmemiş belge: 8 kelime bir altyazıya sığar (2 satır x 4 kelime)
    words = mkwords(["kelime%02d" % i for i in range(16)])
    words[7]["end"] = 5.0  # 1. altyazının son kelimesi, 2. altyazının başını örter
    words[10]["end"] = 6.5  # 2. altyazıda son kelimeden sonra biten kelime
    cues = parse_srt(to_srt(doc(words)))
    assert len(cues) == 2
    prev_end = 0.0
    for _, start, end, _l in cues:
        assert start >= prev_end and end >= start
        prev_end = end
    assert abs(cues[0][2] - 5.0) < 0.002
    assert abs(cues[1][2] - 6.5) < 0.002


def test_srt_tam_7_sn_bolmez():
    # 8.05 - 1.05 kayan noktada 7.000000000000001 olur; tam 7 sn tek altyazı kalmalı
    words = [
        {"i": i, "text": "ab", "start": s, "end": e, "confidence": 0.9, "low_confidence": False}
        for i, (s, e) in enumerate([(1.05, 1.5), (4.0, 4.5), (7.55, 8.05)])
    ]
    assert len(parse_srt(to_srt(doc(words)))) == 1


def test_srt_uzun_cumle_word():
    words = mkwords(LONG)
    cues = parse_srt(to_srt(doc(words)))
    assert len(cues) >= 2
    assert [w for c in cues for l in c[3] for w in l.split()] == LONG
    starts = [w["start"] for w in words]
    assert all(any(abs(c[1] - s) < 0.002 for s in starts) for c in cues)


def test_srt_uzun_cumle_segment():
    d = doc([], timing="segment", segments=[
        {"start": 2.0, "end": 12.0, "text": " ".join(LONG), "word_range": [0, 0]}])
    cues = parse_srt(to_srt(d))
    assert len(cues) >= 2
    assert cues[0][1] >= 2.0 - 0.002 and cues[-1][2] <= 12.0 + 0.002
    for a, b in zip(cues, cues[1:]):
        assert abs(a[2] - b[1]) < 0.002
    assert [w for c in cues for l in c[3] for w in l.split()] == LONG


def test_json_turkce():
    d = doc(mkwords(["ışık"]))
    out = to_json(d)
    assert "ışık" in out and "\\u" not in out
    assert json.loads(out) == d


def test_bos_belge():
    d = doc([])
    assert to_srt(d) == ""
    assert to_txt(d) == ""


def _check_cues(cues):
    for _, start, end, _l in cues:
        assert end >= start and round(end - start, 3) <= 7


def test_srt_tek_kelime_7sn_word():
    w = [{"i": 0, "text": "uzuuun", "start": 1.0, "end": 11.0, "confidence": 0.9, "low_confidence": False}]
    cues = parse_srt(to_srt(doc(w)))
    assert len(cues) == 1
    _check_cues(cues)


def test_srt_tek_kelime_7sn_segment():
    d = doc([], timing="segment", segments=[
        {"start": 1.0, "end": 11.0, "text": "uzuuun", "word_range": [0, 0]}])
    cues = parse_srt(to_srt(d))
    assert len(cues) == 1
    _check_cues(cues)


def test_srt_7sn_nedeniyle_bolunur():
    # 10 kısa kelime, 1 sn aralıkla: 2 satıra sığar, süre 7 sn'yi aşar
    words = [
        {"i": i, "text": "ab", "start": float(i), "end": i + 0.5, "confidence": 0.9, "low_confidence": False}
        for i in range(10)
    ]
    cues = parse_srt(to_srt(doc(words)))
    assert len(cues) >= 2
    assert all(len(c[3]) == 1 for c in cues)
    _check_cues(cues)


def test_timestamp_saat_ve_yuvarlama():
    from autocript.export.formats import _timestamp
    assert _timestamp(3661.0) == "01:01:01,000"
    assert _timestamp(3661.0006) == "01:01:01,001"
    assert _timestamp(59.9996) == "00:01:00,000"


# --- İngilizce kısaltmalar (KT2 Task 4) ---

_FIKSTUR = Path(__file__).resolve().parents[1] / "fixtures" / "ingilizce_kelimeler.json"
_CUMLELER = [
    ("[00:00.00]", "Hi, I'm Dr. Smith."),
    ("[00:01.20]", "Today we test the U.S. version, e.g. the new one."),
    ("[00:04.20]", "Is it fast?"),
    ("[00:05.10]", "Yes!"),
    ("[00:05.40]", "It costs 3.5 dollars..."),
    ("[00:06.60]", "Thanks, Mr. Lee."),
]


def _ingilizce_belge(tek_segment=False):
    ham = json.loads(_FIKSTUR.read_text(encoding="utf-8"))
    rw = [RawWord(x["text"], x["start"], x["end"], x["confidence"]) for x in ham]
    words = [
        {"i": i, "text": x["text"], "start": x["start"], "end": x["end"],
         "confidence": x["confidence"], "low_confidence": False}
        for i, x in enumerate(ham)
    ]
    if tek_segment:
        return doc(words)
    segments = [
        {"start": words[a]["start"], "end": words[b - 1]["end"],
         "text": " ".join(x["text"] for x in words[a:b]), "word_range": [a, b]}
        for a, b in split_segments(rw, [])
    ]
    return doc(words, segments=segments)


def test_ingilizce_txt():
    beklenen = "".join(f"{t} {s}\n" for t, s in _CUMLELER)
    assert to_txt(_ingilizce_belge()) == beklenen
    # Tek uzun segment içinde de kısaltmalar cümleyi bölmez.
    assert to_txt(_ingilizce_belge(tek_segment=True)) == beklenen


def test_kisaltma_tirnak_parantez():
    from autocript.export.formats import _is_long_break, _is_sentence_end
    for tok in ("(e.g.", '"Dr.', "Dr.)", "“Mr.", "(U.S.)", "Prof."):
        assert not _is_sentence_end(tok), tok
        assert not _is_long_break(tok), tok
    assert _is_sentence_end("Done.") and _is_long_break("Done.")
    assert _is_sentence_end('Done."')


def test_uzun_cumle_kisaltma_noktasindan_bolunmez():
    # Mr. noktası 200 karakter sınırından önceki en yakın kırılma noktası olurdu.
    metin = ["x" * 9] * 18 + ["Mr."] + ["y" * 9] * 5 + ["bitti."]
    satirlar = to_txt(doc(mkwords(metin, step=0.1))).splitlines()
    assert not any(s.endswith("Mr.") for s in satirlar)


def test_kisaltma_kumesi():
    assert KISALTMALAR == frozenset(
        {"mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "vs.", "e.g.", "i.e.", "u.s.", "u.k."}
    )
