import asyncio
import os
from pathlib import Path

import pytest

from autocript.storage import job_dir, remove_job_dir, save_upload, sweep
from autocript.types import SourceError


async def _gen(*parts: bytes, boom: bool = False):
    for p in parts:
        yield p
    if boom:
        raise RuntimeError("kesildi")


def test_job_dir_gecersiz_id(tmp_path: Path):
    with pytest.raises(ValueError):
        job_dir(tmp_path, "../x")


def test_upload_guvenli_ad(tmp_path: Path):
    dest = tmp_path / "d"
    dest.mkdir()
    out = asyncio.run(save_upload(_gen(b"abc"), dest, "../../Şarkı Adı.MP4", 100))
    assert out == dest / "upload.mp4"
    assert out.read_bytes() == b"abc"
    assert [p.name for p in tmp_path.iterdir()] == ["d"]
    assert [p.name for p in dest.iterdir()] == ["upload.mp4"]


def test_upload_sinir_asilinca_silinir(tmp_path: Path):
    dest = tmp_path / "d"
    dest.mkdir()
    with pytest.raises(SourceError) as ei:
        asyncio.run(save_upload(_gen(b"x" * 25), dest, "a.mp4", 10))
    assert ei.value.code == "DOSYA_BUYUK"
    assert list(dest.iterdir()) == []
    with pytest.raises(RuntimeError):
        asyncio.run(save_upload(_gen(b"abc", boom=True), dest, "a.mp4", 10))
    assert list(dest.iterdir()) == []


def test_sweep_aktif_dokunmaz(tmp_path: Path):
    a = job_dir(tmp_path, "j_" + "a" * 16)
    b = job_dir(tmp_path, "j_" + "b" * 16)
    c = job_dir(tmp_path, "j_" + "c" * 16)
    now = 1_000_000.0
    os.utime(a, (now - 5000, now - 5000))
    os.utime(b, (now - 5000, now - 5000))
    os.utime(c, (now - 10, now - 10))
    removed = sweep(tmp_path, lambda j: j == "j_" + "a" * 16, now)
    assert removed == ["j_" + "b" * 16]
    assert a.exists() and c.exists() and not b.exists()
    remove_job_dir(tmp_path, "j_" + "b" * 16)


def test_upload_bicim_disi_diske_yazilmaz(tmp_path: Path):
    dest = tmp_path / "d"
    dest.mkdir()
    for ad in ("not.txt", "uzantisiz", None):
        with pytest.raises(SourceError) as e:
            asyncio.run(save_upload(_gen(b"abc"), dest, ad, 100))
        assert e.value.code == "DOSYA_BICIMI"
    assert list(dest.iterdir()) == []
