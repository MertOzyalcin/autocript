"""TXT, SRT ve JSON çıktıları."""
import json

from autocript.metinler import metin
from autocript.transcript.segments import is_abbreviation

MAX_LINE = 42
MAX_LINES = 2
MAX_CUE_S = 7.0
MAX_TXT_LINE = 200
_SENTENCE_END = (".", "?", "!", "…")
_LONG_BREAK = (".", "?", "!", "…", ":", '"', "”")
_CLOSING = '"\'”’)'

# Etiket kaynağın söylediğini yansıtır (katalogda etiket.<kind>): music → müzik; silence yalnızca
# Silero ölçünce; kaynak yalnızca konuşma olmadığını söylediyse "konuşma yok".
_ETIKETLER = ("music", "silence", "unknown")


def _etiket(kind: str, dil: str) -> str:
    return metin(f"etiket.{kind if kind in _ETIKETLER else 'unknown'}", dil)


def to_json(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2)


def stamp(t: float) -> str:
    """[dd:ss.ss]; saniye yüzdeliğe yuvarlanır."""
    cs = round(max(t, 0) * 100)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"[{m:02d}:{s:02d}.{cs:02d}]"


def _is_sentence_end(text: str) -> bool:
    return not is_abbreviation(text) and text.rstrip(_CLOSING).endswith(_SENTENCE_END)


def _is_long_break(text: str) -> bool:
    if is_abbreviation(text):
        return False
    return text.endswith(_LONG_BREAK) or text.rstrip(_CLOSING).endswith(_LONG_BREAK)


def _split_long_sentence(tokens: list[tuple[str, float]]) -> list[tuple[float, str]]:
    """Çok uzun cümleyi en yakın noktalama işaretinden (. ? ! : ") böler; kelime ortasından bölmez."""
    out: list[tuple[float, str]] = []
    rem = tokens
    while rem:
        joined = " ".join(t for t, _ in rem)
        if len(joined) <= MAX_TXT_LINE:
            out.append((rem[0][1], joined))
            break
        best_before: int | None = None
        first_after: int | None = None
        acc = 0
        for i, (tok, _) in enumerate(rem[:-1]):
            acc += len(tok) + (1 if i > 0 else 0)
            if _is_long_break(tok):
                if acc <= MAX_TXT_LINE:
                    best_before = i
                elif first_after is None:
                    first_after = i
                    break
        cut = best_before if best_before is not None else first_after
        if cut is None:
            out.append((rem[0][1], joined))
            break
        out.append((rem[0][1], " ".join(t for t, _ in rem[: cut + 1])))
        rem = rem[cut + 1 :]
    return out


def _seg_tokens(doc: dict, seg: dict) -> list[tuple[str, float]]:
    if doc.get("timing") == "word":
        words = doc.get("words") or []
        lo, hi = seg.get("word_range") or (0, 0)
        if 0 <= lo < hi <= len(words):
            return [
                (w["text"], w["start"] if w.get("start") is not None else seg["start"])
                for w in words[lo:hi]
            ]
    return [(t, seg["start"]) for t in (seg.get("text") or "").split()]


def to_txt(doc: dict, dil: str = "tr") -> str:
    """Her cümle ve her konuşmasız aralık kendi satırında, zamana göre sıralı.

    Satır cümle sonunda (. ? ! …) biter; çok uzun cümle en yakın noktalama
    işaretinden (. ? ! : ") bölünür. Boş belge boş metin verir.
    """
    events: list[tuple[float, int, dict]] = []
    for seg in doc.get("segments") or []:
        events.append((seg["start"], 0, seg))
    for ns in doc.get("non_speech") or []:
        events.append((ns["start"], 1, ns))
    events.sort(key=lambda e: (e[0], e[1]))

    lines: list[tuple[float, str]] = []
    buf: list[tuple[str, float]] = []

    def flush() -> None:
        nonlocal buf
        if buf:
            lines.extend(_split_long_sentence(buf))
            buf = []

    for start, kind, item in events:
        if kind == 1:
            flush()
            lines.append((start, "[" + _etiket(item["kind"], dil) + "]"))
            continue
        for tok, ts in _seg_tokens(doc, item):
            buf.append((tok, ts))
            if _is_sentence_end(tok):
                flush()
    flush()
    return "".join(f"{stamp(t)} {text}\n" for t, text in lines)


def _timestamp(t: float) -> str:
    ms = round(max(t, 0.0) * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _sentence_tokens(doc: dict, seg: dict) -> list[tuple[str, float, float]]:
    """Cümlenin kelimeleri: (metin, başlangıç, bitiş)."""
    if doc.get("timing") == "word":
        lo, hi = seg["word_range"]
        return [(w["text"], w["start"], max(w["end"], w["start"])) for w in doc["words"][lo:hi]]
    texts = seg["text"].split()
    total = sum(len(t) for t in texts)
    if total == 0:
        return []
    span = seg["end"] - seg["start"]
    out, done = [], 0
    for t in texts:
        a = seg["start"] + span * done / total
        done += len(t)
        out.append((t, a, seg["start"] + span * done / total))
    return out


def _wrap(texts: list[str]) -> list[str]:
    lines: list[str] = []
    for t in texts:
        if lines and len(lines[-1]) + 1 + len(t) <= MAX_LINE:
            lines[-1] += " " + t
        else:
            lines.append(t)
    return lines


def _cues(tokens):
    cur: list[tuple[str, float, float]] = []
    for tok in tokens:
        trial = cur + [tok]
        too_big = (
            len(_wrap([t[0] for t in trial])) > MAX_LINES
            or round(max(t[2] for t in trial) - trial[0][1], 2) > MAX_CUE_S
        )
        if cur and too_big:
            yield cur
            cur = [tok]
        else:
            cur = trial
    if cur:
        yield cur


def to_srt(doc: dict, dil: str = "tr") -> str:
    """SRT'de konuşmasız bölüm satırı yoktur; `dil` TXT ile aynı imza için alınır."""
    blocks = []
    prev_end = 0.0
    for seg in doc.get("segments") or []:
        for cue in _cues(_sentence_tokens(doc, seg)):
            start = max(cue[0][1], prev_end)
            end = min(max(max(t[2] for t in cue), start), start + MAX_CUE_S)
            prev_end = end
            text = "\n".join(_wrap([t[0] for t in cue]))
            blocks.append(f"{len(blocks) + 1}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}\n")
    return "\n".join(blocks)
