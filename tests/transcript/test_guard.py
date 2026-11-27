from autocript.transcript.guard import apply_non_speech_guard, merge_non_speech
from autocript.types import NonSpeech, RawWord


def test_merge():
    a = [NonSpeech(0, 4, "unknown")]
    b = [NonSpeech(2, 6, "music")]
    assert merge_non_speech(a, b) == [NonSpeech(0, 2, "unknown"), NonSpeech(2, 6, "music")]


def _words():
    return [
        RawWord("a", 1.5, 1.8, 0.3),
        RawWord("b", 2.0, 2.2, 0.9),
        RawWord("c", 2.4, 2.6, None),
        RawWord("d", 4.0, 4.3, 0.2),
        RawWord("e", None, None, None),
    ]


def test_guard():
    r = apply_non_speech_guard(_words(), [NonSpeech(1.0, 3.0, "music")], 0.6)
    assert [w.text for w in r.words] == ["b", "c", "d", "e"]
    assert r.flagged == [True, True, False, False]
    assert r.removed == 1
    assert len(r.flagged) == len(r.words)


def test_guard_esik_yok():
    r = apply_non_speech_guard(_words(), [NonSpeech(1.0, 3.0, "music")], None)
    assert [w.text for w in r.words] == ["a", "b", "c", "d", "e"]
    assert r.flagged == [True, True, True, False, False]
    assert r.removed == 0


def test_guard_orta_nokta():
    region = [NonSpeech(1.0, 3.0, "music")]
    # taşan kelime: orta nokta 0.8 bölge dışında -> kalır, işaretsiz
    r = apply_non_speech_guard([RawWord("x", 0.5, 1.1, 0.2)], region, 0.6)
    assert [w.text for w in r.words] == ["x"] and r.flagged == [False] and r.removed == 0
    # orta nokta tam başlangıçta -> içeride (düşük güven çıkarılır)
    r = apply_non_speech_guard([RawWord("y", 0.9, 1.1, 0.2)], region, 0.6)
    assert r.words == [] and r.removed == 1
    # orta nokta tam bitişte -> dışarıda (yarı açık)
    r = apply_non_speech_guard([RawWord("z", 2.9, 3.1, 0.2)], region, 0.6)
    assert [w.text for w in r.words] == ["z"] and r.flagged == [False] and r.removed == 0
