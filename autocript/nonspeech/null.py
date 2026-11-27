"""Hiçbir şey bulmayan dedektör (VAD kapalı yol)."""

from pathlib import Path

from autocript.types import NonSpeech


class NullDetector:
    name = "null"

    def detect(self, flac: Path) -> list[NonSpeech]:
        return []
