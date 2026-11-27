"""STT zinciri: ElevenLabs birincil, Groq yedek."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from autocript import tls
from autocript.config import Settings
from autocript.stt import SttAdapter, SttOutcome
from autocript.stt._errors import stt_hata
from autocript.stt.elevenlabs import ElevenLabsScribe
from autocript.stt.groq import GroqWhisper
from autocript.types import SourceError

log = logging.getLogger(__name__)


class SttChain:
    def __init__(self, primary: SttAdapter, fallback: SttAdapter | None):
        self.primary = primary
        self.fallback = fallback

    def transcribe(self, audio: Path, language: str | None) -> SttOutcome:
        try:
            return SttOutcome(self.primary.transcribe(audio, language), False, None)
        except SourceError as primary_error:
            if self.fallback is None:
                raise
            log.warning(
                "STT yedeğe geçiliyor: %s -> %s (%s)",
                self.primary.name,
                self.fallback.name,
                primary_error.detail,
            )
            try:
                raw = self.fallback.transcribe(audio, language)
            except SourceError as fallback_error:
                log.error(
                    "STT yedek de başarısız: %s: %s; %s: %s",
                    self.primary.name,
                    primary_error.detail,
                    self.fallback.name,
                    fallback_error.detail,
                )
                detail = (
                    f"{self.primary.name}: {primary_error.detail}; "
                    f"{self.fallback.name}: {fallback_error.detail}"
                )
                for err in (primary_error, fallback_error):
                    if err.code == "ANAHTAR_REDDEDILDI":
                        raise SourceError(
                            err.code,
                            err.message,
                            detail=detail,
                            upload_fallback=False,
                            params=err.params,
                            varyant=err.varyant,
                        ) from fallback_error
                raise stt_hata("STT_HATA", detail) from fallback_error
            return SttOutcome(raw, True, primary_error)


def build_stt_chain(s: Settings) -> SttChain:
    def client() -> httpx.Client:
        return httpx.Client(timeout=s.stt_timeout_s, verify=tls.ssl_context())

    engines: list[SttAdapter] = []
    if s.elevenlabs_api_key:
        engines.append(ElevenLabsScribe(s.elevenlabs_api_key, client=client()))
    if s.groq_api_key:
        engines.append(GroqWhisper(s.groq_api_key, client=client()))
    if not engines:
        raise RuntimeError("STT anahtarı yok")
    return SttChain(engines[0], engines[1] if len(engines) > 1 else None)
