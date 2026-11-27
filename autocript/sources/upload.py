"""UploadSource: kullanıcının yüklediği dosyayı doğrular (ses izi, süre)."""

from __future__ import annotations

from autocript.audio import probe
from autocript.sources.hatalar import hata
from autocript.types import JobRequest, SourceMeta, SourceResult


class UploadSource:
    def __init__(self, max_duration_s: float):
        self.max_duration_s = max_duration_s

    def resolve(self, request: JobRequest) -> SourceResult:
        path = request.upload_path
        if path is None:
            raise hata("DOSYA_BOZUK", varyant="kayip")
        info = probe(path)
        if not info.has_audio:
            raise hata("DOSYA_SES_YOK", varyant="yukleme")
        if info.duration_s > self.max_duration_s:
            raise hata("VIDEO_UZUN", detail=f"süre {info.duration_s:.1f} sn")
        meta = SourceMeta(
            kind="upload", url=None, platform_id=None, title=None, author=None,
            published_at=None, duration_s=round(info.duration_s, 2),
            stats={"views": None, "likes": None, "comments": None},
        )
        return SourceResult(meta=meta, audio_path=path, transcript=None)
