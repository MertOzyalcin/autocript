"""Groq Whisper adaptörü (OpenAI uyumlu uç nokta)."""

from __future__ import annotations

from pathlib import Path

import httpx

from autocript import tls
from autocript.stt._errors import stt_error
from autocript.stt._lang import to_iso1
from autocript.types import NonSpeech, RawTranscript, RawWord

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
NO_SPEECH_ESIGI = 0.6


class GroqWhisper:
    name = "groq"

    def __init__(self, api_key: str, model: str = "whisper-large-v3", client: httpx.Client | None = None):
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=120, verify=tls.ssl_context())

    def transcribe_raw(self, audio: Path, language: str | None) -> dict:
        data = {
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"],
        }
        if language:
            data["language"] = language
        try:
            with open(audio, "rb") as f:
                resp = self.client.post(
                    URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data=data,
                    files={"file": (Path(audio).name, f)},
                )
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, OSError, ValueError) as e:
            raise stt_error("Groq", e, [self.api_key]) from e

    @staticmethod
    def parse(raw: dict) -> RawTranscript:
        words = [
            RawWord(w["word"], w.get("start"), w.get("end"), None)
            for w in raw.get("words") or []
        ]
        non_speech = [
            NonSpeech(s["start"], s["end"], "unknown")
            for s in raw.get("segments") or []
            if s.get("no_speech_prob", 0) >= NO_SPEECH_ESIGI
        ]
        return RawTranscript(
            language=to_iso1(raw.get("language") or ""),
            timing="word",
            words=words,
            segments=[],
            non_speech=non_speech,
            provider="groq",
            model="whisper-large-v3",
            cost_usd=None,
        )

    def transcribe(self, audio: Path, language: str | None) -> RawTranscript:
        return self.parse(self.transcribe_raw(audio, language))
