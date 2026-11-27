"""Yerel erişim koruması: Host, Origin ve oturum çerezi (saf ASGI)."""

from __future__ import annotations

import hmac
import json
import secrets
from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qs

from starlette.requests import cookie_parser

from autocript.metinler import hata_metni, istek_dili

_EK_BASLIKLAR = [
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", b"frame-ancestors 'none'"),
    (b"referrer-policy", b"no-referrer"),
]


@dataclass(frozen=True)
class Oturum:
    token: str
    port: int

    @classmethod
    def yeni(cls, port: int) -> "Oturum":
        return cls(token=secrets.token_urlsafe(32), port=port)


def cookie_name(port: int) -> str:
    return f"autocript_oturum_{port}"


def _esit(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class LocalGuard:
    def __init__(self, app, oturum: Oturum) -> None:
        self.app = app
        self.oturum = oturum
        port = oturum.port
        self._hostlar = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self._originler = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
        self._cookie = cookie_name(port)

    async def __call__(self, scope, receive, send) -> None:
        tur = scope["type"]
        if tur == "lifespan":
            await self.app(scope, receive, send)
            return
        if tur == "websocket":
            await receive()
            await send({"type": "websocket.close", "code": 1008})
            return
        if tur != "http":
            return

        async def send_ek(mesaj):
            if mesaj["type"] == "http.response.start":
                mesaj = dict(mesaj)
                mesaj["headers"] = list(mesaj.get("headers", [])) + _EK_BASLIKLAR
            await send(mesaj)

        await self._http(scope, receive, send_ek)

    async def _http(self, scope, receive, send) -> None:
        basliklar = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope["headers"]
        }
        dil = istek_dili(scope)
        yontem = scope["method"]
        yol = scope["path"]

        # 2. Host
        if basliklar.get("host", "").lower() not in self._hostlar:
            await self._json(send, 400, "GECERSIZ_HOST", dil)
            return
        # 3. Origin (yalnızca yazma istekleri)
        if yontem not in ("GET", "HEAD"):
            if basliklar.get("origin", "").lower() not in self._originler:
                await self._json(send, 403, "GECERSIZ_KAYNAK", dil)
                return
        # 4. Açılış
        if yontem == "GET" and yol == "/":
            sorgu = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            if "t" in sorgu:
                if _esit(sorgu["t"][0], self.oturum.token):
                    await self._yonlendir(send)
                else:
                    await self._html(send, dil)
                return
        # 5. Çerez
        cerez = cookie_parser(basliklar.get("cookie", "")).get(self._cookie)
        if cerez is None or not _esit(cerez, self.oturum.token):
            if yol.startswith("/api/"):
                await self._json(send, 401, "OTURUM_YOK", dil)
            else:
                await self._html(send, dil)
            return
        await self.app(scope, receive, send)

    async def _json(self, send, durum: int, kod: str, dil: str) -> None:
        govde = json.dumps(
            {"code": kod, "message": hata_metni(kod, dil)}, ensure_ascii=False
        ).encode("utf-8")
        await self._yanit(
            send, durum, govde, [(b"content-type", b"application/json")]
        )

    async def _html(self, send, dil: str) -> None:
        sayfa = (
            f'<!doctype html><html lang="{dil}"><head><meta charset="utf-8">'
            "<title>autocript</title></head>"
            f'<body><p>{escape(hata_metni("OTURUM_YOK", dil))}</p></body></html>'
        ).encode("utf-8")
        await self._yanit(
            send, 401, sayfa, [(b"content-type", b"text/html; charset=utf-8")]
        )

    async def _yonlendir(self, send) -> None:
        cerez = (
            f"{self._cookie}={self.oturum.token}; HttpOnly; SameSite=Strict; Path=/"
        )
        await self._yanit(
            send,
            303,
            b"",
            [
                (b"location", b"/"),
                (b"set-cookie", cerez.encode("latin-1")),
            ],
        )

    async def _yanit(self, send, durum: int, govde: bytes, basliklar) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": durum,
                "headers": basliklar
                + [(b"content-length", str(len(govde)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": govde})
