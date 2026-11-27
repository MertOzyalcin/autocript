"""Web API: yükleme, iş durumu, indirmeler ve sayfa (spec 6.5, 6.6)."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import dataclasses
import html
import json
import logging
import re
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from python_multipart import MultipartParser
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import parse_options_header
from starlette.requests import ClientDisconnect

from autocript.audio import configure_tools
from autocript.config import UPLOAD_EXTS, Settings
from autocript.export import to_json, to_srt, to_txt
from autocript.jobs.pipeline import make_detector, resolve_source, transcribe_result
from autocript.jobs.runner import JobRunner
from autocript.jobs.store import JobStore
from autocript.links.parse import parse_link
from autocript.metinler import (
    dil_sec,
    hata_metni,
    istek_dili,
    katalog_ui,
    uyari_metni,
    yerellestir_hata,
)
from autocript.sources.instapuller import InstapullerSource
from autocript.sources.site_sira import SiteSiralari
from autocript.sources.upload import UploadSource
from autocript.storage import job_dir, new_job_id, remove_job_dir, save_upload, sweep
from autocript.stt.chain import build_stt_chain
from autocript.types import JobRequest, SourceError
from autocript.web.kurulum import register_kurulum
from autocript.yerel.guvenlik import LocalGuard, Oturum

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
SWEEP_INTERVAL_S = 600

MAX_LINK_BODY = 4096  # JSON link gövdesi üst sınırı (İL §6.7)
_FORMATS = {
    "json": (lambda doc, dil: to_json(_belge_dili(doc, dil)), "application/json"),
    "txt": (to_txt, "text/plain; charset=utf-8"),
    "srt": (to_srt, "application/x-subrip; charset=utf-8"),
}


_YER_TUTUCU = re.compile(r"\{\{(ui\.[a-z_.]+)\}\}")


def _html_kacis(deger: str) -> str:
    # Apostrof olduğu gibi kalır (öznitelikler çift tırnaklıdır); < > & ve " kaçışlanır.
    return html.escape(deger, quote=False).replace('"', "&quot;")


def sayfa(ad: str, dil: str, ek: dict[str, str]) -> str:
    """`static/<ad>.html` dosyasını `dil` ile doldurur (KT2 Task 6).

    `{{ui.anahtar}}` yer tutucuları katalogdan, kaçışlanarak gelir. Katalog `</head>` öncesine
    `<script type="application/json">` olarak gömülür; JSON içindeki `<` karakteri `\\u003c` olur.
    `ek` içindeki anahtarlar (`__MAX_UPLOAD_MB__` gibi) metin olarak yerine konur.
    """
    dil = dil_sec(dil)
    katalog = katalog_ui(dil)
    metin = (STATIC_DIR / f"{ad}.html").read_text(encoding="utf-8")
    metin = _YER_TUTUCU.sub(lambda m: _html_kacis(katalog.get(m.group(1), m.group(1))), metin)
    metin = metin.replace("__DIL__", dil)
    for anahtar, deger in ek.items():
        metin = metin.replace(anahtar, deger)
    gomulu = json.dumps(katalog, ensure_ascii=False).replace("<", "\\u003c")
    blok = f'<script id="metinler" type="application/json">{gomulu}</script>\n'
    return metin.replace("</head>", blok + "</head>", 1)


def _belge_dili(doc: dict, dil: str) -> dict:
    """Saklanan belgenin kopyasında yalnızca `warnings[].message` isteğin diline çevrilir.

    Katalogda karşılığı olmayan (ileride eklenen) bir kod için saklanan metin korunur.
    """
    out = copy.deepcopy(doc)
    for w in out.get("warnings") or []:
        m = uyari_metni(w.get("code", ""), dil)
        if m != f"uyari.{w.get('code', '')}":
            w["message"] = m
    return out


class _InvalidRequest(Exception):
    pass


class _BodyTooLarge(Exception):
    pass


async def _read_json_body(request: Request) -> bytes:
    """Gövdeyi okurken sınırı uygular; büyük gövde hiç tamamen belleğe alınmaz."""
    parts: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_LINK_BODY:
            raise _BodyTooLarge()
        parts.append(chunk)
    return b"".join(parts)


class _MultipartFile:
    """Çok parçalı gövdeyi akış hâlinde ayrıştırır; yalnızca `file` parçasının baytlarını verir.

    Hiçbir şey belleğe ya da OS geçici klasörüne toplanmaz.
    """

    def __init__(self, request: Request):
        ctype = request.headers.get("content-type", "")
        main, params = parse_options_header(ctype.encode("latin-1", "replace"))
        boundary = params.get(b"boundary")
        if main != b"multipart/form-data" or not boundary:
            raise _InvalidRequest()
        self._body = request.stream().__aiter__()
        self._pending: list[bytes] = []
        self._ended = False
        self._hfield = b""
        self._hvalue = b""
        self._headers: dict[bytes, bytes] = {}
        self._in_file = False
        self._file_seen = False
        self._file_done = False
        self.filename: str | None = None
        self._parser = MultipartParser(
            boundary,
            {
                "on_part_begin": self._part_begin,
                "on_header_field": self._header_field,
                "on_header_value": self._header_value,
                "on_header_end": self._header_end,
                "on_headers_finished": self._headers_finished,
                "on_part_data": self._part_data,
                "on_part_end": self._part_end,
            },
        )

    # --- ayrıştırıcı geri çağrıları ---
    def _part_begin(self) -> None:
        self._headers = {}
        self._hfield = b""
        self._hvalue = b""
        self._in_file = False

    def _header_field(self, data: bytes, start: int, end: int) -> None:
        self._hfield += data[start:end]

    def _header_value(self, data: bytes, start: int, end: int) -> None:
        self._hvalue += data[start:end]

    def _header_end(self) -> None:
        self._headers[self._hfield.lower()] = self._hvalue
        self._hfield = b""
        self._hvalue = b""

    def _headers_finished(self) -> None:
        _, opts = parse_options_header(self._headers.get(b"content-disposition", b""))
        name = opts.get(b"name", b"").decode("utf-8", "replace")
        if name != "file" or self._file_seen:
            raise _InvalidRequest()
        self._file_seen = True
        self._in_file = True
        fn = opts.get(b"filename")
        if not fn:  # dosya adı yoksa düz form alanıdır, dosya değil (Argon 004)
            raise _InvalidRequest()
        self.filename = fn.decode("utf-8", "replace")

    def _part_data(self, data: bytes, start: int, end: int) -> None:
        if self._in_file and end > start:
            self._pending.append(data[start:end])

    def _part_end(self) -> None:
        if self._in_file:
            self._file_done = True
        self._in_file = False

    # --- akış ---
    async def _pump(self) -> bool:
        """Gövdeden bir parça okur ve ayrıştırır; gövde bittiyse False döner."""
        try:
            chunk = await self._body.__anext__()
        except StopAsyncIteration:
            try:
                self._parser.finalize()
            except FormParserError:
                raise _InvalidRequest() from None
            if not self._file_done:
                raise _InvalidRequest()
            self._ended = True
            return False
        try:
            self._parser.write(chunk)
        except FormParserError:
            raise _InvalidRequest() from None
        return True

    async def start(self) -> None:
        """`file` parçasının başlıkları okunana kadar ilerler."""
        while not self._file_seen:
            if not await self._pump():
                break
        if not self._file_seen:
            raise _InvalidRequest()

    async def chunks(self) -> AsyncIterator[bytes]:
        while True:
            while self._pending:
                yield self._pending.pop(0)
            if self._ended:
                return
            await self._pump()


def _error(
    status: int, code: str, dil: str, *, varyant: str | None = None, **params: str
) -> JSONResponse:
    """Hata yanıtı; metin katalogdan, isteğin diliyle üretilir."""
    return JSONResponse(
        {"code": code, "message": hata_metni(code, dil, params or None, varyant)},
        status_code=status,
    )


def create_app(
    settings: Settings,
    *,
    runner: JobRunner | None = None,
    store: JobStore | None = None,
    oturum: Oturum | None = None,
    env_path: Path | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    configure_tools(settings.ffmpeg_bin, settings.ffprobe_bin)
    if store is None:
        store = JobStore(settings.media_dir / "autocript.db")

    # STT zinciri tembel kurulur: ilk işte ya da anahtar kaydedilince yenilenir.
    chain_lock = threading.Lock()
    chain_holder: list = [None]

    def get_chain():
        with chain_lock:
            if chain_holder[0] is None:
                chain_holder[0] = build_stt_chain(settings)
            return chain_holder[0]

    def reset_chain() -> None:
        with chain_lock:
            chain_holder[0] = None

    # Site başına bir sıra, tek kaynak: her sitenin 15 sn aralığı uygulama genelinde paylaşılır.
    link_kaynagi = InstapullerSource(settings, SiteSiralari())

    own_runner = runner is None
    if runner is None:
        source = UploadSource(settings.max_duration_s)
        detector = make_detector(settings)

        def prepare(req, on_stage, on_meta):
            return resolve_source(
                req, upload=source, link=link_kaynagi, on_stage=on_stage, on_meta=on_meta
            )

        def work(req, on_stage, on_meta, prepared):
            return transcribe_result(
                req,
                prepared,
                stt=get_chain(),
                detector=detector,
                low_conf_threshold=settings.low_confidence_threshold,
                on_stage=on_stage,
            )

        runner = JobRunner(
            store, work, settings.media_dir, settings.job_concurrency, prepare=prepare
        )

    media_dir = settings.media_dir
    max_bytes = settings.max_upload_mb * 1024 * 1024

    def do_sweep() -> None:
        sweep(media_dir, store.is_active, time.time())

    async def sweep_loop() -> None:
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_S)
            try:
                await asyncio.to_thread(do_sweep)
            except Exception:
                log.exception("temizlik turu basarisiz")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            store.mark_interrupted()
            await asyncio.to_thread(do_sweep)
        except Exception:
            log.exception("acilis temizligi basarisiz")
        task = asyncio.create_task(sweep_loop())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    register_kurulum(
        app,
        settings,
        env_path=env_path,
        http_transport=http_transport,
        on_keys_changed=reset_chain,
    )

    async def _post_link(request: Request):
        """JSON `{"url"}` link yolu (İL §6.7). Geçersiz istekte iş kaydı açılmaz."""
        dil = istek_dili(request)
        try:
            raw = await _read_json_body(request)
        except _BodyTooLarge:
            return _error(413, "GECERSIZ_ISTEK", dil)
        except ClientDisconnect:
            return Response(status_code=400)
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = None
        url = body.get("url") if isinstance(body, dict) else None
        if not isinstance(url, str):
            return _error(400, "GECERSIZ_ISTEK", dil)
        try:
            parsed = parse_link(url)
        except SourceError as e:
            return _error(422, e.code, dil, **(e.params or {}))
        if own_runner:
            try:
                await asyncio.to_thread(get_chain)
            except Exception:
                log.exception("stt zinciri kurulamadi")
                return _error(500, "BEKLENMEYEN_HATA", dil)
        job_id = new_job_id()
        dest = job_dir(media_dir, job_id)
        try:
            store.create(job_id)
        except BaseException:
            remove_job_dir(media_dir, job_id)
            raise
        await runner.submit(
            JobRequest(job_id=job_id, work_dir=dest, url=parsed.canonical_url, upload_path=None)
        )
        return {"job_id": job_id}

    @app.post("/api/jobs", status_code=202)
    async def post_job(request: Request):
        dil = istek_dili(request)
        if not settings.elevenlabs_api_key:
            return _error(409, "KURULUM_GEREKLI", dil)
        main, _ = parse_options_header(request.headers.get("content-type", "").encode("latin-1", "replace"))
        if main == b"application/json":
            return await _post_link(request)
        if own_runner:  # zincir yükleme başlamadan kurulur; hata iş kaydı açılmadan döner
            try:
                await asyncio.to_thread(get_chain)
            except Exception:
                log.exception("stt zinciri kurulamadi")
                return _error(500, "BEKLENMEYEN_HATA", dil)
        job_id = new_job_id()
        dest = job_dir(media_dir, job_id)
        try:
            up = _MultipartFile(request)
            await up.start()
            upload_path = await save_upload(up.chunks(), dest, up.filename, max_bytes)
            store.create(job_id)
        except _InvalidRequest:
            remove_job_dir(media_dir, job_id)
            return _error(400, "GECERSIZ_ISTEK", dil)
        except ClientDisconnect:
            remove_job_dir(media_dir, job_id)
            log.info("yukleme yarida kesildi: %s", job_id)
            return Response(status_code=400)
        except SourceError as e:
            remove_job_dir(media_dir, job_id)
            if e.code == "DOSYA_BUYUK":
                return _error(413, e.code, dil, varyant=e.varyant)
            if e.code == "DOSYA_BICIMI":
                return _error(415, e.code, dil)
            log.exception("yukleme hatasi")
            return _error(500, "BEKLENMEYEN_HATA", dil)
        except BaseException:
            remove_job_dir(media_dir, job_id)
            raise
        await runner.submit(
            JobRequest(job_id=job_id, work_dir=dest, url=None, upload_path=upload_path)
        )
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str, request: Request):
        dil = istek_dili(request)
        status = store.get(job_id)
        if status is None:
            return _error(404, "IS_YOK", dil)
        out = dataclasses.asdict(status)
        if out["error"]:
            out["error"] = yerellestir_hata(out["error"], dil)
        return out

    @app.get("/api/jobs/{job_id}/transcript.{ext}")
    async def get_transcript(job_id: str, ext: str, request: Request):
        dil = istek_dili(request)
        status = store.get(job_id)
        if status is None or ext not in _FORMATS:
            return _error(404, "IS_YOK", dil)
        doc = store.get_transcript(job_id) if status.state == "bitti" else None
        if doc is None:
            return _error(409, "IS_BITMEDI", dil)
        render, media_type = _FORMATS[ext]
        return Response(
            render(doc, dil),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="transkript-{job_id}.{ext}"'},
        )

    @app.get("/kurulum")
    async def kurulum_sayfasi(request: Request):
        return HTMLResponse(sayfa("kurulum", istek_dili(request), {}))

    @app.get("/")
    async def index(request: Request):
        if not settings.elevenlabs_api_key:
            return RedirectResponse("/kurulum", status_code=303)
        ek = {
            "__MAX_UPLOAD_MB__": str(settings.max_upload_mb),
            "__UPLOAD_EXTS__": ",".join(UPLOAD_EXTS),
        }
        return HTMLResponse(sayfa("index", istek_dili(request), ek))

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    if oturum is not None:
        app.add_middleware(LocalGuard, oturum=oturum)
    return app
