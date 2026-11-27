"""Anahtar kurulumu uç noktaları: okuma, kaydetme ve sağlayıcı testi."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from autocript import tls
from autocript.config import Settings
from autocript.metinler import istek_dili, metin
from autocript.yerel.anahtarlar import PROVIDERS, check_key, mask, normalize_key, write_env_keys

_ATTR = {"elevenlabs": "elevenlabs_api_key", "groq": "groq_api_key"}


def _durum(settings: Settings) -> dict:
    out = {}
    for name, attr in _ATTR.items():
        value = getattr(settings, attr) or None
        out[name] = {"set": value is not None, "masked": mask(value)}
    return out


async def _json_govde(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def register_kurulum(
    app: FastAPI,
    settings: Settings,
    *,
    env_path: Path | None,
    http_transport: httpx.AsyncBaseTransport | None,
    on_keys_changed: Callable[[], None],
) -> None:
    def bad(request: Request, kod: str) -> JSONResponse:
        """400 GECERSIZ_ISTEK; metin `kurulum.<kod>` anahtarından, istek diliyle."""
        return JSONResponse(
            {"code": "GECERSIZ_ISTEK", "message": metin(f"kurulum.{kod}", istek_dili(request))},
            status_code=400,
        )

    @app.get("/api/saglik")
    async def saglik():
        return {"ok": True}

    @app.get("/api/kurulum")
    async def get_kurulum():
        return _durum(settings)

    @app.put("/api/kurulum")
    async def put_kurulum(request: Request):
        body = await _json_govde(request)
        if body is None or not set(body) <= set(PROVIDERS):
            return bad(request, "ISTEK_BICIMI")
        updates: dict[str, str | None] = {}
        for name, value in body.items():
            if not isinstance(value, str):
                return bad(request, "BICIM")
            if value.strip() == "" and name == "groq":
                updates[name] = None
                continue
            if value.strip() == "":
                return bad(request, "ZORUNLU")
            try:
                updates[name] = normalize_key(value)
            except ValueError:
                return bad(request, "BICIM")
        if "elevenlabs" not in updates and not settings.elevenlabs_api_key:
            return bad(request, "ZORUNLU")
        if updates:
            if env_path is not None:
                write_env_keys(env_path, {PROVIDERS[n]: v for n, v in updates.items()})
            for name, value in updates.items():
                setattr(settings, _ATTR[name], value)
            on_keys_changed()
        return _durum(settings)

    @app.post("/api/kurulum/test")
    async def test_kurulum(request: Request):
        body = await _json_govde(request)
        dil = istek_dili(request)
        provider = body.get("provider") if body else None
        if provider not in PROVIDERS:
            return bad(request, "ISTEK_BICIMI")
        raw = body.get("key")
        if raw is not None and not isinstance(raw, str):
            return bad(request, "ISTEK_BICIMI")
        if raw is not None and raw.strip():
            try:
                key = normalize_key(raw)
            except ValueError:
                return {"ok": False, "message": metin("kurulum.GECERSIZ", dil)}
        else:
            key = getattr(settings, _ATTR[provider]) or None
            if key is None:
                return {"ok": False, "message": metin("kurulum.ONCE_YAPISTIR", dil)}
        async with httpx.AsyncClient(
            transport=http_transport, timeout=10.0, verify=tls.ssl_context()
        ) as client:
            result = await check_key(provider, key, client)
        return {
            "ok": result.ok,
            "message": metin(f"kurulum.{result.kod}", dil, status=str(result.status)),
        }
