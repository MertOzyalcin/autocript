import asyncio

import httpx
import pytest

from autocript.yerel.anahtarlar import (
    CheckResult,
    check_key,
    mask,
    normalize_key,
    write_env_keys,
)

OK = "CALISIYOR"
GECERSIZ = "GECERSIZ"
AG = "AG"
KEY = "sk_" + "a" * 30


def _check(provider, handler):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await check_key(provider, KEY, c)

    return asyncio.run(run())


def test_anahtar_kirpilir():
    assert normalize_key("  sk_" + "a" * 40 + "\n") == "sk_" + "a" * 40


@pytest.mark.parametrize(
    "bad",
    [
        "sk_" + "a" * 20 + "\nGROQ_API_KEY=x",
        "abc",
        "sk_" + "a" * 10 + " " + "b" * 10,
        "sk_" + "a" * 20 + "=x",
    ],
)
def test_anahtar_satir_sonu_reddedilir(bad):
    with pytest.raises(ValueError):
        normalize_key(bad)


def test_mask():
    assert mask("sk_0123456789abcdefa3f9") == "sk_…a3f9"
    assert mask(None) is None
    assert mask("kisa") == "…"


def test_env_yazimi_korur(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "# yorum\nYOUTUBE_API_KEY=y\nELEVENLABS_API_KEY=eski\nELEVENLABS_API_KEY=eski2\nGROQ_API_KEY=g\n",
        encoding="utf-8",
    )
    write_env_keys(p, {"ELEVENLABS_API_KEY": "yeni...", "GROQ_API_KEY": None})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines == ["# yorum", "YOUTUBE_API_KEY=y", "ELEVENLABS_API_KEY=yeni..."]
    assert not list(tmp_path.glob("*.tmp"))


def test_env_yoksa_olusturur(tmp_path):
    p = tmp_path / ".env"
    write_env_keys(p, {"GROQ_API_KEY": "abc", "ELEVENLABS_API_KEY": None})
    assert p.read_text(encoding="utf-8").splitlines() == ["GROQ_API_KEY=abc"]


def test_check_elevenlabs():
    def make(status, body=None, exc=None):
        def h(req):
            assert str(req.url) == "https://api.elevenlabs.io/v1/user"
            assert req.headers["xi-api-key"] == KEY
            if exc:
                raise exc
            return httpx.Response(status, json=body or {})

        return h

    cases = [
        (make(200), True, OK),
        (make(401, {"detail": {"status": "invalid_api_key"}}), False, GECERSIZ),
        (make(401, {"detail": {"status": "missing_permissions"}}), True, OK),
        (make(500), False, "BEKLENMEYEN"),
        (make(0, exc=httpx.ConnectError("x")), False, AG),
    ]
    for h, ok, kod in cases:
        beklenen = CheckResult(ok, kod, 500 if kod == "BEKLENMEYEN" else None)
        assert _check("elevenlabs", h) == beklenen


def test_check_groq():
    def h200(req):
        assert str(req.url) == "https://api.groq.com/openai/v1/models"
        assert req.headers["authorization"] == f"Bearer {KEY}"
        return httpx.Response(200, json={})

    assert _check("groq", h200) == CheckResult(True, OK)
    assert _check("groq", lambda r: httpx.Response(401)) == CheckResult(False, GECERSIZ)
    assert _check("groq", lambda r: httpx.Response(403)) == CheckResult(False, GECERSIZ)
    assert _check("groq", lambda r: httpx.Response(500)) == CheckResult(False, "BEKLENMEYEN", 500)

    def to(req):
        raise httpx.ReadTimeout("t")

    assert _check("groq", to) == CheckResult(False, AG)


def test_check_mesajda_govde_yok():
    for prov, st in [("elevenlabs", 401), ("groq", 401), ("groq", 500), ("elevenlabs", 500)]:
        r = _check(prov, lambda req, st=st: httpx.Response(st, text=f"echo {KEY}"))
        assert KEY not in repr(r)
