"""STT adaptörleri (Görev 4) ve zincir sonucu (KT1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from autocript.types import RawTranscript, SourceError


class SttAdapter(Protocol):
    name: str

    def transcribe(self, audio: Path, language: str | None) -> RawTranscript: ...


@dataclass
class SttOutcome:
    """SttChain.transcribe sonucu: ham transkript ve yedeğe geçilip geçilmediği."""

    raw: RawTranscript
    used_fallback: bool
    primary_error: SourceError | None
