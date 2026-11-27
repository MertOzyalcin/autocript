"""Ham transkriptten şema v1 belgesi (spec 6.2 ve 6.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from autocript.metinler import uyari_metni
from autocript.transcript.guard import apply_non_speech_guard, merge_non_speech
from autocript.transcript.segments import group_minutes, split_segments
from autocript.types import NonSpeech, RawTranscript, RawWord, SourceMeta


def _r(x: float) -> float:
    return round(float(x), 2)


def _timed_words(raw: RawTranscript, merged: list[NonSpeech], threshold: float | None):
    """Sıralar, zamanı tutarlı yapar, korumayı uygular. (kelime listesi, işaretler) döndürür."""
    words = sorted(raw.words, key=lambda w: w.start if w.start is not None else 0.0)
    cleaned = []
    for w in words:
        s = _r(max(w.start or 0.0, 0.0))
        e = _r(max(w.end if w.end is not None else s, s))
        cleaned.append(RawWord(w.text, s, e, w.confidence))
    # Örtüşen kelime zamanları: önceki kelime, sonrakinin başladığı anda biter (Argon 004).
    for prev, cur in zip(cleaned, cleaned[1:]):
        if cur.start < prev.end:
            prev.end = max(prev.start, cur.start)
    res = apply_non_speech_guard(cleaned, merged, threshold)
    return res.words, res.flagged


def _word_dict(i: int, w: RawWord, low: bool) -> dict:
    return {"i": i, "text": w.text, "start": w.start, "end": w.end, "confidence": w.confidence, "low_confidence": low}


def _fix_order(segments: list[dict]) -> None:
    for prev, cur in zip(segments, segments[1:]):
        if cur["start"] < prev["end"]:
            prev["end"] = max(cur["start"], prev["start"])


def build(
    raw: RawTranscript,
    meta: SourceMeta,
    job_id: str,
    vad_non_speech: list[NonSpeech],
    *,
    low_conf_threshold: float | None,
    route: Literal["stt", "gemini_youtube"] = "stt",
    warnings: list[dict] | None = None,
    now: datetime | None = None,
) -> dict:
    """Şema v1'e uyan sözlük döndürür."""
    merged = merge_non_speech(vad_non_speech, raw.non_speech)
    out_warnings: list[dict] = []
    words: list[dict] = []
    segments: list[dict] = []
    any_flagged = False

    if raw.timing == "segment":
        segs = sorted(raw.segments, key=lambda s: s.start)
        for s in segs:
            tokens = s.text.split()
            if not tokens:
                continue
            a = _r(max(s.start, 0.0))
            lo = len(words)
            for t in tokens:
                words.append(_word_dict(len(words), RawWord(t, None, None, None), False))
            segments.append(
                {"start": a, "end": _r(max(s.end, a)), "text": " ".join(tokens), "word_range": [lo, len(words)]}
            )
    else:
        kept, flagged = _timed_words(raw, merged, low_conf_threshold)
        any_flagged = any(flagged)
        for i, (w, f) in enumerate(zip(kept, flagged)):
            low = f or (
                w.confidence is not None and low_conf_threshold is not None and w.confidence < low_conf_threshold
            )
            words.append(_word_dict(i, w, low))
        for a, b in split_segments(kept, merged):
            segments.append(
                {
                    "start": kept[a].start,
                    "end": max(w.end for w in kept[a:b]),
                    "text": " ".join(w.text for w in kept[a:b]),
                    "word_range": [a, b],
                }
            )
    _fix_order(segments)

    duration = max(meta.duration_s or 0.0, segments[-1]["end"] if segments else 0.0)
    minutes = group_minutes(segments, duration)

    if not words:
        out_warnings.append({"code": "KONUSMA_YOK", "message": uyari_metni("KONUSMA_YOK", "tr")})
    if any_flagged:
        out_warnings.append(
            {"code": "KONUSMA_DISI_KELIME", "message": uyari_metni("KONUSMA_DISI_KELIME", "tr")}
        )
    out_warnings.extend(warnings or [])

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    language = raw.language if len(raw.language) >= 2 else "und"
    stats = meta.stats or {}
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "created_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "kind": meta.kind,
            "url": meta.url,
            "platform_id": meta.platform_id,
            "title": meta.title,
            "author": meta.author,
            "published_at": meta.published_at,
            "duration_s": meta.duration_s,
            "stats": {k: stats.get(k) for k in ("views", "likes", "comments")},
        },
        "engine": {"route": route, "provider": raw.provider, "model": raw.model},
        "language": language,
        "timing": raw.timing,
        "words": words,
        "segments": segments,
        "minutes": minutes,
        "non_speech": [{"start": _r(n.start), "end": _r(n.end), "kind": n.kind} for n in merged],
        "warnings": out_warnings,
    }
