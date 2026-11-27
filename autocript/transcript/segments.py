"""Cümle bölme ve dakika gruplama (spec 6.2 ve 6.3)."""

from __future__ import annotations

import math

from autocript.types import NonSpeech, RawWord

MAX_GAP_S = 0.7
MAX_CHARS = 84
MAX_DURATION_S = 7.0
_ENDINGS = (".", "!", "?", "…")
KISALTMALAR = frozenset(
    {"mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "vs.", "e.g.", "i.e.", "u.s.", "u.k."}
)
_SARMAL = "\"'“”‘’()"


def is_abbreviation(text: str) -> bool:
    """Kelime bir kısaltmaysa True; baştaki ve sondaki tırnak/parantez atılır, büyük/küçük harf yok sayılır."""
    return text.strip(_SARMAL).lower() in KISALTMALAR


def _mid(w: RawWord) -> float:
    return (w.start + w.end) / 2


def split_segments(words: list[RawWord], non_speech: list[NonSpeech]) -> list[tuple[int, int]]:
    """Zamanlı, start'a göre sıralı kelimeleri yarı açık [ilk, son+1) cümle aralıklarına böler."""
    ranges: list[tuple[int, int]] = []
    if not words:
        return ranges
    first = 0
    length = len(words[0].text)
    for i in range(1, len(words)):
        prev, cur = words[i - 1], words[i]
        split = (
            (prev.text.endswith(_ENDINGS) and not is_abbreviation(prev.text))
            or round(cur.start - prev.end, 2) > MAX_GAP_S
            or length + 1 + len(cur.text) > MAX_CHARS
            or round(cur.end - words[first].start, 2) > MAX_DURATION_S
            or any(_mid(prev) < n.start <= _mid(cur) for n in non_speech)
        )
        if split:
            ranges.append((first, i))
            first = i
            length = len(cur.text)
        else:
            length += 1 + len(cur.text)
    ranges.append((first, len(words)))
    return ranges


def group_minutes(segments: list[dict], duration_s: float) -> list[dict]:
    """Her cümle başladığı dakikaya yazılır; boş dakika [k, k] aralığı alır."""
    count = max(1, math.ceil(duration_s / 60))
    if segments:
        count = max(count, int(segments[-1]["start"] // 60) + 1)
    minutes: list[dict] = []
    idx = 0
    for m in range(count):
        lo = idx
        while idx < len(segments) and int(segments[idx]["start"] // 60) <= m:
            idx += 1
        minutes.append(
            {
                "minute": m,
                "start": round(float(m * 60), 2),
                "end": round(min((m + 1) * 60, duration_s), 2),
                "text": " ".join(s["text"] for s in segments[lo:idx]),
                "segment_range": [lo, idx],
            }
        )
    return minutes
