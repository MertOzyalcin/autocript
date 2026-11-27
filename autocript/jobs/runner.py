"""JobRunner: işleri sınırlı eşzamanlılıkla arka planda çalıştırır."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from autocript.links.parse import parse_link
from autocript.metinler import hata_metni
from autocript.jobs.store import RESTART_ERROR, JobStore
from autocript.storage import remove_job_dir
from autocript.types import JobRequest, SourceError, SourceMeta, SourceResult

log = logging.getLogger(__name__)

Work = Callable[..., dict]  # prepare yoksa 3 argüman, varsa dördüncüsü `prepared`
Prepare = Callable[[JobRequest, Callable[[str], None], Callable[[SourceMeta], None]], SourceResult]


class JobRunner:
    def __init__(
        self, store: JobStore, work: Work, media_dir: Path, concurrency: int,
        prepare: Prepare | None = None,
    ):
        self._store = store
        self._work = work
        self._media_dir = media_dir
        self._concurrency = concurrency
        self._prepare = prepare
        self._sem: asyncio.Semaphore | None = None
        self._tasks: set[asyncio.Task] = set()

    async def submit(self, request: JobRequest) -> None:
        if self._sem is None:
            self._sem = asyncio.Semaphore(self._concurrency)
        task = asyncio.create_task(self._run(request))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, request: JobRequest) -> None:
        job_id = request.job_id
        store = self._store
        try:
            on_stage = lambda stage: store.update(job_id, stage=stage)  # noqa: E731
            on_meta = lambda meta: store.update(job_id, meta=meta)  # noqa: E731
            prepared = None
            if self._prepare is not None:
                # Kaynak çözme (Instagram sırası dahil) iş yuvası semaforunun dışında:
                # kilitte bekleyen link işleri dosya yüklemelerini bekletmez.
                store.update(job_id, state="calisiyor")
                prepared = await asyncio.to_thread(self._prepare, request, on_stage, on_meta)
            async with self._sem:
                store.update(job_id, state="calisiyor")
                args = (request, on_stage, on_meta)
                if self._prepare is not None:
                    args += (prepared,)
                doc = await asyncio.to_thread(self._work, *args)
                store.save_transcript(job_id, doc)
                self._cleanup(job_id)  # durum görünmeden klasör silinmiş olsun (Argon 004)
                store.update(job_id, state="bitti")
        except SourceError as e:
            log.warning("is %s hata: code=%s detail=%s", job_id, e.code, e.detail)
            error = {
                "code": e.code,
                "message": e.message,
                "upload_fallback": e.upload_fallback,
            }
            params = dict(e.params) if e.params else {}
            varyant = e.varyant
            if request.url:
                error["url"] = request.url
                try:
                    params["site"] = parse_link(request.url).platform
                except SourceError:
                    pass
                # "yukleme" metinleri dosya yüklemeye özgü; link işinde genel metin gösterilir.
                if varyant == "yukleme":
                    varyant = None
            if params:
                error["params"] = params
            if varyant:
                error["varyant"] = varyant
            self._fail(job_id, error)
        except asyncio.CancelledError:
            log.warning("is %s iptal edildi", job_id)
            self._fail(job_id, RESTART_ERROR)
            raise
        except Exception:
            log.exception("is %s beklenmeyen hata", job_id)
            self._fail(
                job_id,
                {
                    "code": "BEKLENMEYEN_HATA",
                    "message": hata_metni("BEKLENMEYEN_HATA", "tr"),
                    "upload_fallback": False,
                },
            )
        finally:
            self._cleanup(job_id)  # yedek: beklenmeyen çıkışlar için

    def _cleanup(self, job_id: str) -> None:
        try:
            remove_job_dir(self._media_dir, job_id)
        except Exception:
            log.exception("is %s klasoru silinemedi", job_id)

    def _fail(self, job_id: str, error: dict) -> None:
        self._cleanup(job_id)
        try:
            self._store.update(job_id, state="hata", error=error)
        except Exception:
            log.exception("is %s hata durumu yazilamadi", job_id)
