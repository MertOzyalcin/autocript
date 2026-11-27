"""Konuşmasız bölüm dedektörleri: NullDetector, SileroDetector (Görev 5)."""

from pathlib import Path
from typing import Protocol

from autocript.types import NonSpeech


class NonSpeechDetector(Protocol):
    name: str

    def detect(self, flac: Path) -> list[NonSpeech]: ...
