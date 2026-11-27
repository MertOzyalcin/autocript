"""Anahtar deposu: doğrulama, maskeleme, .env yazımı ve sağlayıcı testi."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

PROVIDERS: dict[str, str] = {
    "elevenlabs": "ELEVENLABS_API_KEY",
    "groq": "GROQ_API_KEY",
}

_KEY_RE = re.compile(r"[A-Za-z0-9_.\-]{16,200}")
TIMEOUT = 10.0

def normalize_key(value: str) -> str:
    key = value.strip()
    if not _KEY_RE.fullmatch(key):
        raise ValueError("Anahtar biçimi geçersiz.")
    return key


def mask(key: str | None) -> str | None:
    if key is None:
        return None
    if len(key) >= 12:
        return key[:3] + "…" + key[-4:]
    return "…"


def write_env_keys(env_path: Path, updates: dict[str, str | None]) -> None:
    env_path = Path(env_path)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    out: list[str] = []
    done: set[str] = set()
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if name in updates:
            if name in done:
                continue  # yinelenen satır
            done.add(name)
            if updates[name] is not None:
                out.append(f"{name}={updates[name]}")
            continue
        out.append(line)
    for name, value in updates.items():
        if name not in done and value is not None:
            out.append(f"{name}={value}")
    tmp = env_path.with_name(env_path.name + ".tmp")
    tmp.write_text("".join(f"{ln}\n" for ln in out), encoding="utf-8")
    os.replace(tmp, env_path)


@dataclass
class CheckResult:
    """Sonuç kodu; ekrandaki metin `kurulum.<kod>` katalog anahtarından, istek diliyle gelir."""

    ok: bool
    kod: Literal["CALISIYOR", "GECERSIZ", "AG", "BEKLENMEYEN"]
    status: int | None = None


def _other(status: int) -> CheckResult:
    return CheckResult(False, "BEKLENMEYEN", status)


async def check_key(provider: str, key: str, client: httpx.AsyncClient) -> CheckResult:
    if provider not in PROVIDERS:
        raise ValueError(f"Bilinmeyen sağlayıcı: {provider}")
    try:
        if provider == "elevenlabs":
            resp = await client.get(
                "https://api.elevenlabs.io/v1/user",
                headers={"xi-api-key": key},
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                return CheckResult(True, "CALISIYOR")
            if resp.status_code == 401:
                if _missing_permissions(resp):
                    return CheckResult(True, "CALISIYOR")
                return CheckResult(False, "GECERSIZ")
            return _other(resp.status_code)
        resp = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        return CheckResult(False, "AG")
    if resp.status_code == 200:
        return CheckResult(True, "CALISIYOR")
    if resp.status_code in (401, 403):
        return CheckResult(False, "GECERSIZ")
    return _other(resp.status_code)


def _missing_permissions(resp: httpx.Response) -> bool:
    try:
        detail = resp.json().get("detail")
        return isinstance(detail, dict) and detail.get("status") == "missing_permissions"
    except Exception:
        return False
