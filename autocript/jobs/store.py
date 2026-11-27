"""İş deposu: SQLite, WAL, iş parçacığı başına bağlantı."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from autocript.metinler import hata_metni
from autocript.types import JobStatus, SourceMeta

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    stage TEXT,
    error TEXT,
    meta TEXT,
    transcript TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

RESTART_ERROR = {
    "code": "SUNUCU_YENIDEN_BASLADI",
    "message": hata_metni("SUNUCU_YENIDEN_BASLADI", "tr"),
    "upload_fallback": True,
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class JobStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(db_path)
        self._local = threading.local()
        conn = self._conn()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._path, timeout=5.0, isolation_level=None)
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def create(self, job_id: str) -> None:
        now = _now()
        self._conn().execute(
            "INSERT INTO jobs (job_id, state, created_at, updated_at) VALUES (?, 'sirada', ?, ?)",
            (job_id, now, now),
        )

    def update(
        self,
        job_id: str,
        *,
        state: str | None = None,
        stage: str | None = None,
        error: dict | None = None,
        meta: SourceMeta | None = None,
    ) -> None:
        sets: list[str] = []
        args: list = []
        if state is not None:
            sets.append("state = ?")
            args.append(state)
        if stage is not None:
            sets.append("stage = ?")
            args.append(stage)
        if error is not None:
            sets.append("error = ?")
            args.append(json.dumps(error, ensure_ascii=False))
        if meta is not None:
            sets.append("meta = ?")
            args.append(json.dumps(asdict(meta), ensure_ascii=False))
        sets.append("updated_at = ?")
        args.append(_now())
        args.append(job_id)
        self._conn().execute(f"UPDATE jobs SET {', '.join(sets)} WHERE job_id = ?", args)

    def get(self, job_id: str) -> JobStatus | None:
        row = self._conn().execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return JobStatus(
            job_id=row["job_id"],
            state=row["state"],
            stage=row["stage"],
            error=json.loads(row["error"]) if row["error"] else None,
            meta=SourceMeta(**json.loads(row["meta"])) if row["meta"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_transcript(self, job_id: str, doc: dict) -> None:
        self._conn().execute(
            "UPDATE jobs SET transcript = ?, updated_at = ? WHERE job_id = ?",
            (json.dumps(doc, ensure_ascii=False), _now(), job_id),
        )

    def get_transcript(self, job_id: str) -> dict | None:
        row = self._conn().execute(
            "SELECT transcript FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None or row["transcript"] is None:
            return None
        return json.loads(row["transcript"])

    def is_active(self, job_id: str) -> bool:
        row = self._conn().execute("SELECT state FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return row is not None and row["state"] in ("sirada", "calisiyor")

    def mark_interrupted(self) -> int:
        cur = self._conn().execute(
            "UPDATE jobs SET state = 'hata', error = ?, updated_at = ? "
            "WHERE state IN ('sirada', 'calisiyor')",
            (json.dumps(RESTART_ERROR, ensure_ascii=False), _now()),
        )
        return cur.rowcount
