"""Kaynaklar: UploadSource, InstapullerSource (spec 6.2)."""

from typing import Protocol

from autocript.types import JobRequest, SourceResult


class Source(Protocol):
    def resolve(self, request: JobRequest) -> SourceResult:
        """Kaynağı çözer; hata olursa SourceError atar."""
        ...
