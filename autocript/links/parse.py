"""Shorts/Reels link tanıma ve kanonik adres üretimi."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from autocript.sources.hatalar import hata
from autocript.types import ParsedLink, SourceError

_YT_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_IG_CODE = re.compile(r"(?=[A-Za-z0-9_-]*[A-Za-z0-9])[A-Za-z0-9_-]{5,}")  # en az bir harf/rakam
_YT_HOSTS = {"youtube.com", "youtu.be"}
_IG_HOSTS = {"instagram.com"}


def _gecersiz(url: str) -> SourceError:
    return hata("LINK_GECERSIZ")


def _yt(video_id: str, kind: str) -> ParsedLink:
    return ParsedLink(
        platform="youtube",
        platform_id=video_id,
        kind=kind,  # type: ignore[arg-type]
        canonical_url=f"https://www.youtube.com/watch?v={video_id}",
    )


def parse_link(url: str) -> ParsedLink:
    """Shorts/Reels linkini tanır; geçersizse SourceError("LINK_GECERSIZ")."""
    raw = (url or "").strip()
    if not raw:
        raise _gecersiz(url)
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        raise _gecersiz(url) from None
    if parts.scheme not in ("http", "https"):
        raise _gecersiz(url)
    # Kullanıcı bilgisi ve 80/443 dışı port reddedilir (İL §6.7; instapuller da reddediyor).
    if "@" in parts.netloc or (port is not None and port not in (80, 443)):
        raise _gecersiz(url)
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    segs = [s for s in parts.path.split("/") if s]

    if host in _YT_HOSTS:
        if host == "youtu.be":
            if len(segs) >= 1 and _YT_ID.fullmatch(segs[0]):
                return _yt(segs[0], "watch")
        else:
            if len(segs) == 2 and segs[0] == "shorts" and _YT_ID.fullmatch(segs[1]):
                return _yt(segs[1], "short")
            if segs == ["watch"]:
                vid = (parse_qs(parts.query).get("v") or [""])[0]
                if _YT_ID.fullmatch(vid):
                    return _yt(vid, "watch")
    elif host in _IG_HOSTS:
        # /reel/<kod>, /reels/<kod>, /<hesap>/reel/<kod>, /p/<kod>
        if len(segs) == 3:
            segs = segs[1:]
        if len(segs) == 2 and _IG_CODE.fullmatch(segs[1]):
            if segs[0] in ("reel", "reels"):
                return ParsedLink(
                    "instagram", segs[1], "reel",
                    f"https://www.instagram.com/reel/{segs[1]}/",
                )
            if segs[0] == "p":
                return ParsedLink(
                    "instagram", segs[1], "post",
                    f"https://www.instagram.com/p/{segs[1]}/",
                )
    raise _gecersiz(url)
