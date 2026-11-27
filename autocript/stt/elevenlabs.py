"""ElevenLabs Scribe adaptörü (POST /v1/speech-to-text)."""

from __future__ import annotations

import math
from pathlib import Path

import httpx

from autocript import tls
from autocript.stt._errors import stt_error
from autocript.stt._lang import to_iso1
from autocript.types import NonSpeech, RawTranscript, RawWord

URL = "https://api.elevenlabs.io/v1/speech-to-text"


class ElevenLabsScribe:
    name = "elevenlabs"

    def __init__(self, api_key: str, model: str = "scribe_v3", client: httpx.Client | None = None):
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=120, verify=tls.ssl_context())

    def transcribe_raw(self, audio: Path, language: str | None) -> dict:
        data = {
            "model_id": self.model,
            "timestamps_granularity": "word",
            "tag_audio_events": "true",
        }
        if language:
            data["language_code"] = language
        try:
            with open(audio, "rb") as f:
                resp = self.client.post(
                    URL,
                    headers={"xi-api-key": self.api_key},
                    data=data,
                    files={"file": (Path(audio).name, f)},
                )
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, OSError, ValueError) as e:
            raise stt_error("ElevenLabs", e, [self.api_key]) from e

    @staticmethod
    def parse(raw: dict) -> RawTranscript:
        words: list[RawWord] = []
        non_speech: list[NonSpeech] = []
        for w in raw.get("words") or []:
            kind = w.get("type", "word")
            if kind == "word":
                lp = w.get("logprob")
                conf = None if lp is None else min(1.0, max(0.0, math.exp(lp)))
                words.append(RawWord(w["text"], w.get("start"), w.get("end"), conf))
            elif kind == "audio_event":
                text = (w.get("text") or "").lower()
                k = "music" if ("music" in text or "müzik" in text) else "unknown"
                if w.get("start") is not None and w.get("end") is not None:
                    non_speech.append(NonSpeech(w["start"], w["end"], k))
        return RawTranscript(
            language=to_iso1(raw.get("language_code") or ""),
            timing="word",
            words=words,
            segments=[],
            non_speech=non_speech,
            provider="elevenlabs",
            model="scribe_v3",
            cost_usd=None,
        )

    def transcribe(self, audio: Path, language: str | None) -> RawTranscript:
        return self.parse(self.transcribe_raw(audio, language))
