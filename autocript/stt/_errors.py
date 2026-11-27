"""STT adaptörleri için ortak hata üretimi: ayrıntı + anahtar maskeleme."""

from __future__ import annotations

from collections.abc import Iterable

import httpx

from autocript.metinler import hata_metni
from autocript.sources.hatalar import FALLBACK
from autocript.types import SourceError

MIN_GIZLI = 4
GOVDE_LIMIT = 500


def redact(text: str, secrets: Iterable[str | None]) -> str:
    for s in secrets:
        if s and len(s) >= MIN_GIZLI:
            text = text.replace(s, "***")
    return text


def stt_hata(
    kod: str, detail: str | None = None, *, provider: str | None = None
) -> SourceError:
    """Katalog mesajıyla STT hatası; provider verilirse params olarak taşınır."""
    params = {"provider": provider} if provider else None
    return SourceError(
        kod,
        hata_metni(kod, "tr", params),
        upload_fallback=FALLBACK[kod],
        detail=detail,
        params=params,
    )


def stt_error(provider: str, exc: Exception, secrets: Iterable[str | None]) -> SourceError:
    secrets = list(secrets)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        body = redact(exc.response.text, secrets)[:GOVDE_LIMIT]
        detail = f"HTTP {status}: {body}"
        if status in (401, 403):
            return stt_hata("ANAHTAR_REDDEDILDI", detail, provider=provider)
    else:
        detail = redact(f"{type(exc).__name__}: {exc}", secrets)[:GOVDE_LIMIT]
    return stt_hata("STT_HATA", detail)
