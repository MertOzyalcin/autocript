"""İşlem hattı: kaynak → ses → transkript → son."""

from __future__ import annotations

from collections.abc import Callable

from autocript.audio import to_flac
from autocript.config import Settings
from autocript.metinler import uyari_metni
from autocript.nonspeech import NonSpeechDetector
from autocript.nonspeech.null import NullDetector
from autocript.sources.hatalar import hata
from autocript.sources.instapuller import InstapullerSource
from autocript.sources.upload import UploadSource
from autocript.stt.chain import SttChain
from autocript.transcript import build
from autocript.types import JobRequest, SourceMeta, SourceResult

# Saklanan belgede Türkçe metin durur (şema `message` ister); ekrandaki dil yanıt anında seçilir.
YEDEK_UYARI = {"code": "YEDEK_MOTOR", "message": uyari_metni("YEDEK_MOTOR", "tr")}
ANAHTAR_UYARI = {"code": "ANAHTAR_REDDEDILDI", "message": uyari_metni("ANAHTAR_REDDEDILDI", "tr")}


def _yedek_uyarilari(outcome) -> list[dict] | None:
    if not outcome.used_fallback:
        return None
    uyarilar = []
    if outcome.primary_error is not None and outcome.primary_error.code == "ANAHTAR_REDDEDILDI":
        uyarilar.append(dict(ANAHTAR_UYARI))
    uyarilar.append(dict(YEDEK_UYARI))
    return uyarilar


def make_detector(s: Settings) -> NonSpeechDetector:
    if s.nonspeech_detector != "silero":
        return NullDetector()
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "Konuşmasız bölüm dedektörü kurulu değil. baslat.cmd'yi kapatıp yeniden açın."
        ) from e
    from autocript.nonspeech.silero import SileroDetector

    return SileroDetector()


def resolve_source(
    request: JobRequest,
    *,
    upload: UploadSource,
    link: InstapullerSource | None,
    on_stage: Callable[[str], None],
    on_meta: Callable[[SourceMeta], None] | None = None,
) -> SourceResult:
    """Kaynağı seçip çözer. Semafor dışında çalışabilir (JobRunner.prepare)."""
    if request.url:
        if link is None:
            raise hata("IG_ARAC_YOK")
        # Aşamaları ("sira", "kaynak") InstapullerSource kendisi bildirir; geri dönüş olmasın.
        result = link.resolve(request, on_stage)
    else:
        on_stage("kaynak")
        result = upload.resolve(request)
    if on_meta is not None:
        on_meta(result.meta)
    return result


def transcribe_result(
    request: JobRequest,
    result: SourceResult,
    *,
    stt: SttChain,
    detector: NonSpeechDetector,
    low_conf_threshold: float | None,
    on_stage: Callable[[str], None],
) -> dict:
    """Ses → STT → transkript belgesi (semafor içinde çalışır)."""
    on_stage("ses")
    # Kaynak dosyayı zaten probe etti ve ses izini doğruladı; ikinci ffprobe yok.
    flac = to_flac(result.audio_path, request.work_dir / "audio.flac", check_audio=False)
    vad = detector.detect(flac)

    on_stage("transkript")
    outcome = stt.transcribe(flac, language=None)

    on_stage("son")
    return build(
        outcome.raw, result.meta, request.job_id, vad,
        low_conf_threshold=low_conf_threshold,
        warnings=_yedek_uyarilari(outcome),
    )


def run_pipeline(
    request: JobRequest,
    *,
    source: UploadSource,
    stt: SttChain,
    detector: NonSpeechDetector,
    low_conf_threshold: float | None,
    on_stage: Callable[[str], None],
    on_meta: Callable[[SourceMeta], None] | None = None,
) -> dict:
    result = resolve_source(
        request, upload=source, link=None, on_stage=on_stage, on_meta=on_meta
    )
    return transcribe_result(
        request, result, stt=stt, detector=detector,
        low_conf_threshold=low_conf_threshold, on_stage=on_stage,
    )
