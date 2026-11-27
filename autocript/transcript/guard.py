"""Uydurma koruması: konuşmasız bölgedeki düşük güvenli kelimeleri ayıklar, kalanları işaretler."""

from __future__ import annotations

from dataclasses import dataclass

from autocript.types import NonSpeech, NonSpeechKind, RawWord

_PRIORITY: dict[NonSpeechKind, int] = {"music": 2, "silence": 1, "unknown": 0}


@dataclass
class GuardResult:
    words: list[RawWord]
    flagged: list[bool]
    removed: int


def merge_non_speech(a: list[NonSpeech], b: list[NonSpeech]) -> list[NonSpeech]:
    """İki listeyi örtüşmesiz, sıralı birleştirir; çakışmada music > silence > unknown."""
    items = [*a, *b]
    points = sorted({p for n in items for p in (n.start, n.end)})
    out: list[NonSpeech] = []
    for lo, hi in zip(points, points[1:]):
        kinds = [n.kind for n in items if n.start <= lo and n.end >= hi]
        if not kinds:
            continue
        kind = max(kinds, key=_PRIORITY.__getitem__)
        if out and out[-1].kind == kind and out[-1].end == lo:
            out[-1].end = hi
        else:
            out.append(NonSpeech(lo, hi, kind))
    return out


def apply_non_speech_guard(
    words: list[RawWord], non_speech: list[NonSpeech], threshold: float | None
) -> GuardResult:
    """Orta noktası bölgeye (yarı açık) düşen kelime: güveni eşiğin altındaysa çıkarılır; kalan işaretlenir.

    Zamansız kelimelere dokunulmaz. threshold None ise hiçbir kelime çıkarılmaz.
    """
    kept: list[RawWord] = []
    flagged: list[bool] = []
    removed = 0
    for w in words:
        inside = (
            w.start is not None
            and w.end is not None
            and any(n.start <= (w.start + w.end) / 2 < n.end for n in non_speech)
        )
        if inside and threshold is not None and w.confidence is not None and w.confidence < threshold:
            removed += 1
            continue
        kept.append(w)
        flagged.append(inside)
    return GuardResult(kept, flagged, removed)
