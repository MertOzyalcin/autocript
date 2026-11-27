"""Giden HTTPS istekleri için TLS bağlamı.

Windows sertifika deposuna güvenir; HTTPS trafiğini tarayan antivirüsler kendi
kök sertifikalarını sisteme eklediği için bu olmadan istekler bozulur.
`truststore.inject_into_ssl()` kullanılmaz (genel durumu değiştirir).
"""

from __future__ import annotations

import logging
import ssl

log = logging.getLogger(__name__)

_ctx: ssl.SSLContext | None = None


def ssl_context() -> ssl.SSLContext:
    global _ctx
    if _ctx is None:
        try:
            import truststore

            _ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            log.warning(
                "Windows sertifika deposu kullanılamadı; standart sertifika listesine dönüldü."
            )
            _ctx = ssl.create_default_context()
    return _ctx


def _reset_for_tests() -> None:
    global _ctx
    _ctx = None
