import asyncio
import threading
import time

from autocript.jobs.runner import JobRunner
from autocript.jobs.store import JobStore
from autocript.types import JobRequest, SourceError, SourceMeta


JID = "j_aaaaaaaaaaaa"


def _req(media, job_id):
    d = media / "jobs" / job_id
    d.mkdir(parents=True)
    (d / "x.bin").write_bytes(b"x")
    return JobRequest(job_id=job_id, work_dir=d, url=None, upload_path=None)


async def _wait(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        await asyncio.sleep(0.02)
    return False


def _setup(tmp_path, work, concurrency=2):
    store = JobStore(tmp_path / "a.db")
    return store, JobRunner(store, work, tmp_path, concurrency)


def test_runner_basarili(tmp_path):
    meta = SourceMeta(kind="upload", url=None, platform_id=None, title="t", author=None,
                      published_at=None, duration_s=1.0)

    def work(request, on_stage, on_meta):
        on_stage("kaynak")
        on_meta(meta)
        on_stage("son")
        return {"ok": True}

    store, runner = _setup(tmp_path, work)

    async def main():
        store.create(JID)
        req = _req(tmp_path, JID)
        await runner.submit(req)
        assert await _wait(lambda: store.get(JID).state == "bitti")
        return req

    req = asyncio.run(main())
    assert store.get_transcript(JID) == {"ok": True}
    assert store.get(JID).meta == meta
    assert store.get(JID).stage == "son"
    assert not req.work_dir.exists()


def test_runner_source_error(tmp_path):
    def work(request, on_stage, on_meta):
        raise SourceError("VIDEO_UZUN", "Video çok uzun.", detail="gizli ayrıntı")

    store, runner = _setup(tmp_path, work)

    async def main():
        store.create(JID)
        req = _req(tmp_path, JID)
        await runner.submit(req)
        assert await _wait(lambda: store.get(JID).state == "hata")
        return req

    req = asyncio.run(main())
    st = store.get(JID)
    assert st.error == {"code": "VIDEO_UZUN", "message": "Video çok uzun.", "upload_fallback": True}
    assert not req.work_dir.exists()


def test_runner_beklenmeyen(tmp_path):
    def work(request, on_stage, on_meta):
        1 / 0

    store, runner = _setup(tmp_path, work)

    async def main():
        store.create(JID)
        req = _req(tmp_path, JID)
        await runner.submit(req)
        assert await _wait(lambda: store.get(JID).state == "hata")
        return req

    req = asyncio.run(main())
    err = store.get(JID).error
    assert err["code"] == "BEKLENMEYEN_HATA"
    assert err["message"] == "Beklenmeyen bir hata oldu."
    assert err["upload_fallback"] is False
    assert not req.work_dir.exists()


def test_runner_son_durumda_klasor_yok(tmp_path):
    seen = {}

    class Spy(JobStore):
        def update(self, job_id, **kw):
            if kw.get("state") in ("bitti", "hata"):
                seen[job_id] = (tmp_path / "jobs" / job_id).exists()
            super().update(job_id, **kw)

    def work(request, on_stage, on_meta):
        if request.job_id.endswith("2"):
            raise SourceError("VIDEO_UZUN", "Video çok uzun.")
        if request.job_id.endswith("3"):
            1 / 0
        return {"ok": True}

    store = Spy(tmp_path / "a.db")
    runner = JobRunner(store, work, tmp_path, 3)
    ids = [f"j_aaaaaaaaaaa{i}" for i in (1, 2, 3)]

    async def main():
        for j in ids:
            store.create(j)
            await runner.submit(_req(tmp_path, j))
        await asyncio.wait_for(asyncio.gather(*runner._tasks), 5)

    asyncio.run(main())
    assert seen == {j: False for j in ids}


def test_runner_eszamanlilik(tmp_path):
    release = threading.Event()

    def work(request, on_stage, on_meta):
        release.wait(10)
        return {"id": request.job_id}

    store, runner = _setup(tmp_path, work, concurrency=3)

    async def main():
        ids = [f"j_aaaaaaaaaaa{i}" for i in range(4)]
        try:
            for j in ids:
                store.create(j)
                await runner.submit(_req(tmp_path, j))
            assert await _wait(
                lambda: sum(store.get(j).state == "calisiyor" for j in ids) == 3
            )
            t0 = time.monotonic()
            states = sorted(store.get(j).state for j in ids)
            assert time.monotonic() - t0 < 0.5
            assert states == ["calisiyor"] * 3 + ["sirada"]
        finally:
            release.set()
        assert await _wait(lambda: all(store.get(j).state == "bitti" for j in ids))

    asyncio.run(main())


def test_runner_hata_yazimi_basarisiz(tmp_path, caplog):
    def work(request, on_stage, on_meta):
        raise SourceError("VIDEO_UZUN", "Video çok uzun.")

    class BrokenStore(JobStore):
        def update(self, job_id, **kw):
            if kw.get("state") == "hata":
                raise RuntimeError("database is locked")
            super().update(job_id, **kw)

    store = BrokenStore(tmp_path / "a.db")
    runner = JobRunner(store, work, tmp_path, 2)
    unhandled = []

    async def main():
        asyncio.get_running_loop().set_exception_handler(lambda l, c: unhandled.append(c))
        store.create(JID)
        req = _req(tmp_path, JID)
        await runner.submit(req)
        await asyncio.wait_for(asyncio.gather(*runner._tasks), 5)
        return req

    with caplog.at_level("ERROR"):
        req = asyncio.run(main())
    assert not unhandled
    assert any("database is locked" in (r.exc_text or "") for r in caplog.records)
    assert not req.work_dir.exists()


def test_runner_iptal(tmp_path):
    release = threading.Event()

    def work(request, on_stage, on_meta):
        release.wait(10)
        return {}

    store, runner = _setup(tmp_path, work)

    async def main():
        try:
            store.create(JID)
            req = _req(tmp_path, JID)
            await runner.submit(req)
            assert await _wait(lambda: store.get(JID).state == "calisiyor")
            (task,) = list(runner._tasks)
            task.cancel()
            try:
                await asyncio.wait_for(task, 5)
            except asyncio.CancelledError:
                pass
            assert task.cancelled()
            return req
        finally:
            release.set()

    req = asyncio.run(main())
    st = store.get(JID)
    assert st.state == "hata"
    assert st.error["code"] == "SUNUCU_YENIDEN_BASLADI"
    assert st.error["upload_fallback"] is True
    assert not req.work_dir.exists()


# --- prepare (Instagram sırası semafor dışında) ---

from autocript.sources.hatalar import hata  # noqa: E402
from autocript.types import SourceResult  # noqa: E402

IG_URL = "https://www.instagram.com/reel/ABCDE12/"


def _meta():
    return SourceMeta(kind="upload", url=None, platform_id=None, title="t", author=None,
                      published_at=None, duration_s=1.0)


def _link_req(media, job_id):
    r = _req(media, job_id)
    return JobRequest(job_id=job_id, work_dir=r.work_dir, url=IG_URL, upload_path=None)


def _prep_setup(tmp_path, work, prepare, concurrency):
    store = JobStore(tmp_path / "a.db")
    return store, JobRunner(store, work, tmp_path, concurrency, prepare=prepare)


def test_prepare_semafor_disinda(tmp_path):
    release = threading.Event()
    girdi = threading.Semaphore(0)
    calisan_work = []

    def prepare(request, on_stage, on_meta):
        if request.url:
            girdi.release()
            release.wait(10)
        return SourceResult(meta=_meta(), audio_path=None, transcript=None)

    def work(request, on_stage, on_meta, prepared):
        calisan_work.append(request.job_id)
        return {"ok": True}

    store, runner = _prep_setup(tmp_path, work, prepare, concurrency=1)

    async def main():
        link_ids = [f"j_aaaaaaaaaaa{i}" for i in range(3)]
        yukle = "j_aaaaaaaaaaa9"
        try:
            for j in link_ids:
                store.create(j)
                await runner.submit(_link_req(tmp_path, j))
            for _ in link_ids:
                assert await asyncio.to_thread(girdi.acquire, True, 5)
            assert all(store.get(j).state == "calisiyor" for j in link_ids)
            store.create(yukle)
            await runner.submit(_req(tmp_path, yukle))
            assert await _wait(lambda: store.get(yukle).state == "bitti")
            assert calisan_work == [yukle]
        finally:
            release.set()
        assert await _wait(lambda: all(store.get(j).state == "bitti" for j in link_ids))

    asyncio.run(main())


def test_bekleyen_ig_yuklemeyi_tikamaz(tmp_path):
    release = threading.Event()
    girdi = threading.Semaphore(0)

    def prepare(request, on_stage, on_meta):
        if request.url:
            on_stage("sira")
            girdi.release()
            release.wait(10)
        return SourceResult(meta=_meta(), audio_path=None, transcript=None)

    def work(request, on_stage, on_meta, prepared):
        return {"ok": True}

    store, runner = _prep_setup(tmp_path, work, prepare, concurrency=3)

    async def main():
        link_ids = [f"j_aaaaaaaaaaa{i}" for i in range(3)]
        yukle = "j_aaaaaaaaaaa9"
        try:
            for j in link_ids:
                store.create(j)
                await runner.submit(_link_req(tmp_path, j))
            for _ in link_ids:
                assert await asyncio.to_thread(girdi.acquire, True, 5)
            assert all(store.get(j).stage == "sira" for j in link_ids)
            store.create(yukle)
            await runner.submit(_req(tmp_path, yukle))
            assert await _wait(lambda: store.get(yukle).state == "bitti", timeout=1.0)
        finally:
            release.set()
        assert await _wait(lambda: all(store.get(j).state == "bitti" for j in link_ids))

    asyncio.run(main())


def test_prepare_hatasi_url_tasir(tmp_path):
    def prepare(request, on_stage, on_meta):
        raise hata("IG_ERISILEMEDI")

    def work(request, on_stage, on_meta, prepared):
        raise AssertionError("work çağrılmamalı")

    store, runner = _prep_setup(tmp_path, work, prepare, concurrency=1)

    async def main():
        store.create(JID)
        await runner.submit(_link_req(tmp_path, JID))
        assert await _wait(lambda: store.get(JID).state == "hata")

    asyncio.run(main())
    err = store.get(JID).error
    assert err["code"] == "IG_ERISILEMEDI"
    assert err["upload_fallback"] is True
    assert err["url"] == IG_URL
    assert err["params"] == {"site": "instagram"}
    assert set(err) == {"code", "message", "upload_fallback", "url", "params"}


def test_hata_nesnesinde_url_yalniz_linkte(tmp_path):
    def work(request, on_stage, on_meta):
        raise SourceError("VIDEO_UZUN", "Video çok uzun.")

    store, runner = _setup(tmp_path, work)

    async def main():
        store.create(JID)
        await runner.submit(_req(tmp_path, JID))
        assert await _wait(lambda: store.get(JID).state == "hata")

    asyncio.run(main())
    assert "url" not in store.get(JID).error


def test_ig_hata_klasoru_siler(tmp_path):
    def prepare(request, on_stage, on_meta):
        (request.work_dir / "yarim.part").write_bytes(b"x")
        raise hata("IG_ERISILEMEDI")

    store, runner = _prep_setup(tmp_path, lambda *a: {}, prepare, concurrency=1)

    async def main():
        store.create(JID)
        req = _link_req(tmp_path, JID)
        await runner.submit(req)
        assert await _wait(lambda: store.get(JID).state == "hata")
        return req

    req = asyncio.run(main())
    assert not req.work_dir.exists()


def test_prepare_sonucu_work_a_gecer_ve_meta_yazilir(tmp_path):
    sonuc = SourceResult(meta=_meta(), audio_path=None, transcript=None)
    gelen = []

    def prepare(request, on_stage, on_meta):
        on_meta(sonuc.meta)
        return sonuc

    def work(request, on_stage, on_meta, prepared):
        gelen.append(prepared)
        return {"ok": True}

    store, runner = _prep_setup(tmp_path, work, prepare, concurrency=1)

    async def main():
        store.create(JID)
        await runner.submit(_link_req(tmp_path, JID))
        assert await _wait(lambda: store.get(JID).state == "bitti")

    asyncio.run(main())
    assert gelen == [sonuc]
    assert store.get(JID).meta == sonuc.meta
