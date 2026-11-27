"""Ses: ffprobe kontrolü, 16 kHz mono FLAC, PCM (Görev 3).

probe(path) -> ProbeResult: süre ve ses izi; okunamayan dosyada SourceError("DOSYA_BOZUK").
to_flac(path, out, *, check_audio=True) -> Path: 16 kHz mono FLAC; ses izi yoksa SourceError("DOSYA_SES_YOK").
decode_pcm(path) -> np.ndarray: float32, 16 kHz mono, [-1, 1].
configure_tools(ffmpeg_bin, ffprobe_bin) -> None: araç yollarını ayarlar.
"""

from autocript.audio.ffmpeg import configure_tools, decode_pcm, probe, to_flac

__all__ = ["probe", "to_flac", "decode_pcm", "configure_tools"]
