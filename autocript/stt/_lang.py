"""Dil kodu normalleştirme (ISO 639-3 / dil adı -> ISO 639-1)."""

_MAP = {
    "tur": "tr",
    "turkish": "tr",
    "eng": "en",
    "english": "en",
}


def to_iso1(code: str) -> str:
    """Bilinmeyen kod olduğu gibi döner."""
    return _MAP.get(code.strip().lower(), code) if code else code
