import sqlite3

from autocript.jobs.store import JobStore
from autocript.types import SourceMeta


def test_store_yasam_dongusu(tmp_path):
    store = JobStore(tmp_path / "autocript.db")
    store.create("j1")
    st = store.get("j1")
    assert st.state == "sirada" and st.stage is None and st.meta is None
    assert st.created_at.endswith("Z")
    assert store.is_active("j1")
    store.update("j1", state="calisiyor", stage="ses")
    st = store.get("j1")
    assert (st.state, st.stage) == ("calisiyor", "ses")
    doc = {"a": [1, 2], "b": "ç"}
    assert store.get_transcript("j1") is None
    store.save_transcript("j1", doc)
    assert store.get_transcript("j1") == doc
    store.update("j1", state="bitti")
    assert not store.is_active("j1")
    assert store.get("yok") is None


def test_store_wal(tmp_path):
    db = tmp_path / "yeni" / "alt" / "autocript.db"
    JobStore(db)
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.close()


def test_store_meta(tmp_path):
    store = JobStore(tmp_path / "a.db")
    store.create("j1")
    meta = SourceMeta(
        kind="youtube", url="https://y/x", platform_id="x", title="t", author="a",
        published_at="2026-01-01T00:00:00Z", duration_s=12.5,
        stats={"views": 1, "likes": None, "comments": 3},
    )
    store.update("j1", meta=meta)
    assert store.get("j1").meta == meta


def test_store_hata(tmp_path):
    store = JobStore(tmp_path / "a.db")
    store.create("j1")
    err = {"code": "VIDEO_UZUN", "message": "m", "upload_fallback": True}
    store.update("j1", state="hata", error=err)
    assert store.get("j1").error == err


def test_mark_interrupted(tmp_path):
    store = JobStore(tmp_path / "a.db")
    for j in ("a", "b", "c"):
        store.create(j)
    store.update("a", state="calisiyor")
    store.update("b", state="bitti")
    assert store.mark_interrupted() == 2
    a, b, c = store.get("a"), store.get("b"), store.get("c")
    assert a.state == "hata" and a.error["code"] == "SUNUCU_YENIDEN_BASLADI"
    assert c.state == "hata" and c.error["code"] == "SUNUCU_YENIDEN_BASLADI"
    assert b.state == "bitti" and b.error is None
