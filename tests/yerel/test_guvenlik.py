from contextlib import asynccontextmanager

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from autocript.yerel.guvenlik import LocalGuard, Oturum, cookie_name

TOKEN = "T" * 43
PORT = 8000
OTURUM = Oturum(token=TOKEN, port=PORT)
COOKIE = cookie_name(PORT)
BASLIKLAR = {
    "x-frame-options": "DENY",
    "content-security-policy": "frame-ancestors 'none'",
    "referrer-policy": "no-referrer",
}
OK_ORIGIN = {"Origin": "http://127.0.0.1:8000"}
BASE = "http://127.0.0.1:8000"


def _ok(request):
    return PlainTextResponse("ok")


def _api(request):
    return JSONResponse({"ok": True})


def _app(baslangic=None):
    routes = [
        Route("/", _ok),
        Route("/api/x", _api, methods=["GET", "POST"]),
        Route("/static/a.js", _ok),
    ]

    @asynccontextmanager
    async def lifespan(app):
        if baslangic is not None:
            baslangic.append(True)
        yield

    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(LocalGuard, oturum=OTURUM)
    return app


@pytest.fixture
def client():
    with TestClient(_app(), base_url=BASE) as c:
        yield c


@pytest.fixture
def cerezli(client):
    client.cookies.set(COOKIE, TOKEN)
    return client


@pytest.mark.parametrize(
    "host", ["evil.com", "evil.com:8000", "127.0.0.1:9999", "127.0.0.1.evil.com:8000"]
)
def test_host_yabanci_400(cerezli, host):
    r = cerezli.get("/", headers={"Host": host})
    assert r.status_code == 400
    assert r.json()["code"] == "GECERSIZ_HOST"


def test_host_localhost_kabul(cerezli):
    r = cerezli.get("/", headers={"Host": "localhost:8000"})
    assert r.status_code == 200


def test_origin_yok_post_403(cerezli):
    r = cerezli.post("/api/x")
    assert r.status_code == 403
    assert r.json()["code"] == "GECERSIZ_KAYNAK"


def test_origin_yabanci_403(cerezli):
    r = cerezli.post("/api/x", headers={"Origin": "http://evil.com"})
    assert r.status_code == 403


def test_origin_null_403(cerezli):
    r = cerezli.post("/api/x", headers={"Origin": "null"})
    assert r.status_code == 403


def test_origin_dogru_post_kabul(cerezli):
    assert cerezli.post("/api/x", headers=OK_ORIGIN).status_code == 200
    assert (
        cerezli.post("/api/x", headers={"Origin": "http://localhost:8000"}).status_code
        == 200
    )


def test_token_ile_acilis(client):
    r = client.get(f"/?t={TOKEN}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    sc = r.headers["set-cookie"]
    assert f"{COOKIE}={TOKEN}" in sc
    assert "HttpOnly" in sc
    assert "SameSite=Strict" in sc
    assert "Path=/" in sc
    assert client.get("/").status_code == 200


def test_yanlis_token_401(client):
    for t in ("yanlis", "ğ"):
        r = client.get("/", params={"t": t}, follow_redirects=False)
        assert r.status_code == 401
        assert "text/html" in r.headers["content-type"]
    r = client.get("/api/x", headers={"Cookie": f"{COOKIE}=ğ".encode("utf-8")})
    assert r.status_code == 401


def test_cerezsiz_api_401_json(client):
    r = client.get("/api/x")
    assert r.status_code == 401
    assert r.json()["code"] == "OTURUM_YOK"


def test_cerezsiz_sayfa_401_html(client):
    r = client.get("/")
    assert r.status_code == 401
    assert "text/html" in r.headers["content-type"]
    assert "baslat.cmd" in r.text


def test_cerezsiz_statik_401(client):
    assert client.get("/static/a.js").status_code == 401


def test_cerceve_basliklari(cerezli, client):
    r200 = cerezli.get("/")
    assert r200.status_code == 200
    for k, v in BASLIKLAR.items():
        assert r200.headers[k] == v
    cerezli.cookies.clear()
    r401 = cerezli.get("/")
    assert r401.status_code == 401
    for k, v in BASLIKLAR.items():
        assert r401.headers[k] == v
    r400 = cerezli.get("/", headers={"Host": "evil.com"})
    assert r400.status_code == 400
    for k, v in BASLIKLAR.items():
        assert r400.headers[k] == v
    cerezli.cookies.set(COOKIE, TOKEN)
    r403 = cerezli.post("/api/x")
    assert r403.status_code == 403
    for k, v in BASLIKLAR.items():
        assert r403.headers[k] == v


def test_yonlendirme_basliklari(client):
    r = client.get(f"/?t={TOKEN}", follow_redirects=False)
    for k, v in BASLIKLAR.items():
        assert r.headers[k] == v


def test_lifespan_gecer():
    olaylar = []
    with TestClient(_app(olaylar), base_url=BASE):
        assert olaylar == [True]


def test_yeni_oturum():
    a, b = Oturum.yeni(8001), Oturum.yeni(8001)
    assert a.port == 8001 and len(a.token) >= 43 and a.token != b.token
    assert cookie_name(8001) == "autocript_oturum_8001"
