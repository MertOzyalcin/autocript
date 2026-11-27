"""Modüller arası ortak sözleşme (spec 6.2).

Bu dosyayı yalnızca mimar değiştirir. Ajan bir değişiklik gerektiğini düşünürse
durur ve bildirir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ErrorCode = str  # spec 6.4'teki kodlardan biri

NonSpeechKind = Literal["music", "silence", "unknown"]
Timing = Literal["word", "segment"]


@dataclass
class NonSpeech:
    start: float
    end: float
    kind: NonSpeechKind


@dataclass
class RawWord:
    text: str
    start: float | None  # saniye; timing == "segment" ise None
    end: float | None
    confidence: float | None  # 0-1'e normalleştirilmiş; sağlayıcı vermiyorsa None


@dataclass
class RawSegment:
    start: float
    end: float
    text: str


@dataclass
class RawTranscript:
    language: str
    timing: Timing
    words: list[RawWord]  # timing == "word" ise dolu, "segment" ise boş
    segments: list[RawSegment]  # timing == "segment" ise dolu, "word" ise boş
    non_speech: list[NonSpeech]  # sağlayıcının bildirdiği; yoksa boş
    provider: str
    model: str
    cost_usd: float | None


@dataclass
class SourceMeta:
    kind: Literal["upload", "youtube", "instagram"]
    url: str | None
    platform_id: str | None
    title: str | None
    author: str | None
    published_at: str | None  # ISO 8601
    duration_s: float | None
    stats: dict[str, int | None] = field(
        default_factory=lambda: {"views": None, "likes": None, "comments": None}
    )


@dataclass
class JobRequest:
    job_id: str
    work_dir: Path  # data/media/jobs/<job_id>/
    url: str | None
    upload_path: Path | None  # yüklenen dosya, work_dir içinde


@dataclass
class SourceResult:
    meta: SourceMeta
    audio_path: Path | None  # STT yolu: work_dir içinde ham medya
    # Şu an kullanılmıyor (Gemini yolu KT2'de kalktı); ileride doğrudan transkript veren
    # bir kaynak için durur. audio_path ile transcript'ten tam olarak biri dolu.
    transcript: RawTranscript | None


class SourceError(Exception):
    """message: kullanıcıya gösterilebilen kısa açıklama.

    detail: hata ayıklama ayrıntısı (ör. sağlayıcının HTTP durumu ve yanıt gövdesi).
    Kullanıcıya gösterilmez; günlüğe ve str(e)'ye girer. Gizli değerler
    (API anahtarları) detail'e konmadan önce maskelenmiş olmalıdır.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        upload_fallback: bool = True,
        detail: str | None = None,
        *,
        params: dict[str, str] | None = None,
        varyant: str | None = None,
    ):
        text = f"{code}: {message}" + (f" | {detail}" if detail else "")
        super().__init__(text)
        self.code = code
        self.message = message  # Türkçe; günlük için. Ekrandaki metin katalogdan üretilir.
        self.upload_fallback = upload_fallback
        self.detail = detail
        self.params = params  # ör. {"site": "youtube"}, {"provider": "ElevenLabs"}
        self.varyant = varyant  # ör. "yukleme": katalogda hata.<kod>.<varyant>


@dataclass
class JobStatus:  # GET /api/jobs/{id} yanıtı
    job_id: str
    state: Literal["sirada", "calisiyor", "bitti", "hata"]
    stage: Literal["sira", "kaynak", "ses", "transkript", "son"] | None  # "sira": Instagram kilidinde bekliyor
    error: dict | None  # {"code", "message", "upload_fallback", "url"}
    meta: SourceMeta | None  # kaynak çözülünce dolar
    created_at: str
    updated_at: str


# --- Plan Görev 1'in eklediği iki tip (spec'te imzası var, tanımı yoktu) ---


@dataclass
class ProbeResult:
    duration_s: float
    has_audio: bool
    container: str


@dataclass
class ParsedLink:
    platform: Literal["youtube", "instagram"]
    platform_id: str
    kind: Literal["short", "watch", "reel", "post"]
    canonical_url: str
