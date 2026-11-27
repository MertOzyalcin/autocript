import builtins
import importlib
import logging
import ssl

import httpx
import pytest
import truststore
from fastapi.testclient import TestClient

from autocript import tls
from autocript.config import Settings
from autocript.jobs.runner import JobRunner
from autocript.jobs.store import JobStore
from autocript.stt.chain import build_stt_chain
from autocript.web.app import create_app
from autocript.yerel.araclar import ensure_ffmpeg

KEY = "sk_0123456789abcdefa3f9"


@pytest.fixture(autouse=True)
def _temiz_onbellek():
    tls._reset_for_tests()
    yield
    tls._reset_for_tests()


def test_ssl_context_truststore_ve_onbellekli():
    ctx = tls.ssl_context()
    assert isinstance(ctx, truststore.SSLContext)
    assert tls.ssl_context() is ctx


def test_truststore_yoksa_standart_baglam(monkeypatch, caplog):
    gercek = builtins.__import__

    def sahte(name, *a, **k):
        if name == "truststore":
            raise ImportError("yok")
        return gercek(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sahte)
    with caplog.at_level(logging.WARNING, logger="autocript.tls"):
        ctx = tls.ssl_context()
        assert tls.ssl_context() is ctx
    assert isinstance(ctx, ssl.SSLContext)
    assert not isinstance(ctx, truststore.SSLContext)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


class _Kayit(Exception):
    pass


def _isaretle(monkeypatch):
    isaret = object()
    monkeypatch.setattr(tls, "ssl_context", lambda: isaret)
    return isaret


def test_stt_zinciri_baglami_kullanir(monkeypatch):
    isaret = _isaretle(monkeypatch)
    gorulen = []

    def sahte(**kw):
        gorulen.append(kw.get("verify"))
        return object()

    monkeypatch.setattr(httpx, "Client", sahte)
    build_stt_chain(Settings(elevenlabs_api_key="k" * 20, groq_api_key="g" * 20))
    assert gorulen == [isaret, isaret]


@pytest.mark.parametrize(
    "modul,sinif",
    [
        ("elevenlabs", "ElevenLabsScribe"),
        ("groq", "GroqWhisper"),
    ],
)
def test_adaptor_varsayilan_istemci_baglami_kullanir(monkeypatch, modul, sinif):
    isaret = _isaretle(monkeypatch)
    gorulen = []

    def sahte(**kw):
        gorulen.append(kw.get("verify"))
        return object()

    monkeypatch.setattr(httpx, "Client", sahte)
    getattr(importlib.import_module(f"autocript.stt.{modul}"), sinif)("anahtar")
    assert gorulen == [isaret]


def test_ensure_ffmpeg_baglami_kullanir(monkeypatch, tmp_path):
    isaret = _isaretle(monkeypatch)
    gorulen = []

    def sahte(**kw):
        gorulen.append(kw.get("verify"))
        raise _Kayit

    monkeypatch.setattr(httpx, "Client", sahte)
    with pytest.raises(_Kayit):
        ensure_ffmpeg(tmp_path, say=lambda *_: None)
    assert gorulen == [isaret]


def test_kurulum_testi_baglami_kullanir(monkeypatch, tmp_path):
    isaret = _isaretle(monkeypatch)
    gorulen = []
    gercek = httpx.AsyncClient

    def sahte(**kw):
        gorulen.append(kw.pop("verify", None))
        return gercek(**kw)

    monkeypatch.setattr(httpx, "AsyncClient", sahte)
    s = Settings(media_dir=tmp_path / "media", elevenlabs_api_key=KEY)
    store = JobStore(s.media_dir / "autocript.db")
    runner = JobRunner(store, lambda *a: {}, s.media_dir, 2)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    app = create_app(
        s, runner=runner, store=store, env_path=tmp_path / ".env", http_transport=transport
    )
    with TestClient(app) as c:
        assert c.post("/api/kurulum/test", json={"provider": "elevenlabs"}).json()["ok"]
    assert gorulen == [isaret]
