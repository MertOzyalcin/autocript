"""Silero VAD (ONNX) ile konuşmasız bölüm bulma."""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from autocript.audio import decode_pcm
from autocript.config import ROOT
from autocript.types import NonSpeech

if TYPE_CHECKING:
    import numpy as np

MODEL_URL = "https://raw.githubusercontent.com/snakers4/silero-vad/v6.2.3/src/silero_vad/data/silero_vad.onnx"
MODEL_SHA256 = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"
MODEL_NAME = "silero_vad.onnx"

SR = 16000
WINDOW = 512
CONTEXT = 64
SPEECH_THRESHOLD = 0.5
SILENCE_DBFS = -45.0


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as r, dest.open("wb") as f:  # noqa: S310
        f.write(r.read())


def ensure_model(model_dir: Path) -> Path:
    path = model_dir / MODEL_NAME
    if path.exists() and _sha256(path) == MODEL_SHA256:
        return path
    path.unlink(missing_ok=True)  # uyuşmayan/bozuk dosya, indirme başarısız olsa da kalmasın
    model_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=model_dir, suffix=".part")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        _fetch(MODEL_URL, tmp)
        if _sha256(tmp) != MODEL_SHA256:
            raise RuntimeError(
                f"Silero modeli indirildi ama SHA-256 tutmadı (beklenen {MODEL_SHA256}); dosya silindi."
            )
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def gaps_from_speech(
    speech: list[tuple[float, float]], duration: float, min_gap: float = 1.0
) -> list[tuple[float, float]]:
    """Konuşma aralıklarının tamamlayıcısı; min_gap'ten kısa boşluklar atılır."""
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in sorted(speech):
        if s - cursor >= min_gap:
            gaps.append((cursor, s))
        cursor = max(cursor, e)
    if duration - cursor >= min_gap:
        gaps.append((cursor, duration))
    return gaps


def classify_gap(samples: np.ndarray) -> Literal["silence", "unknown"]:
    """RMS -45 dBFS'in altı sessizlik, üstü bilinmeyen (müzik/gürültü olabilir)."""
    import numpy as np

    if samples.size == 0:
        return "silence"
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    dbfs = 20 * np.log10(rms) if rms > 0 else -np.inf
    return "silence" if dbfs < SILENCE_DBFS else "unknown"


class SileroDetector:
    name = "silero"

    def __init__(self, model_dir: Path = ROOT / "data" / "models"):
        self.model_dir = Path(model_dir)
        self._session = None

    def _load(self):
        if self._session is None:
            import onnxruntime as ort

            path = ensure_model(self.model_dir)
            self._session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        return self._session

    def _speech_probs(self, pcm: np.ndarray) -> np.ndarray:
        import numpy as np

        sess = self._load()
        names = {i.name for i in sess.get_inputs()}
        in_name = "input" if "input" in names else next(iter(names))
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros(CONTEXT, dtype=np.float32)
        n = int(np.ceil(len(pcm) / WINDOW))
        padded = np.zeros(n * WINDOW, dtype=np.float32)
        padded[: len(pcm)] = pcm
        out_names = [o.name for o in sess.get_outputs()]
        probs = np.zeros(n, dtype=np.float32)
        for i in range(n):
            chunk = padded[i * WINDOW : (i + 1) * WINDOW]
            x = np.concatenate([context, chunk])[None, :].astype(np.float32)
            feeds = {in_name: x, "state": state}
            if "sr" in names:
                feeds["sr"] = np.array(SR, dtype=np.int64)
            out = sess.run(out_names, feeds)
            probs[i] = float(np.asarray(out[0]).reshape(-1)[0])
            state = out[1]
            context = x[0, -CONTEXT:]
        return probs

    def detect(self, flac: Path) -> list[NonSpeech]:
        self._load()  # model eksik/bozuksa ses çözülmeden önce hata ver
        pcm = decode_pcm(flac)
        duration = len(pcm) / SR
        probs = self._speech_probs(pcm)
        speech: list[tuple[float, float]] = []
        start = None
        for i, p in enumerate(probs):
            if p >= SPEECH_THRESHOLD and start is None:
                start = i * WINDOW / SR
            elif p < SPEECH_THRESHOLD and start is not None:
                speech.append((start, i * WINDOW / SR))
                start = None
        if start is not None:
            speech.append((start, duration))
        result = []
        for s, e in gaps_from_speech(speech, duration):
            seg = pcm[int(s * SR) : int(e * SR)]
            result.append(NonSpeech(s, e, classify_gap(seg)))
        return result
