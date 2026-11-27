import pytest

from autocript.links import parse_link
from autocript.types import SourceError

YT = "https://www.youtube.com/watch?v=abcdefghijk"
IG_REEL = "https://www.instagram.com/reel/C1a2B3c4D5e/"
IG_POST = "https://www.instagram.com/p/C1a2B3c4D5e/"


@pytest.mark.parametrize(
    "girdi, beklenen",
    [
        ("https://www.youtube.com/shorts/abcdefghijk", ("youtube", "abcdefghijk", "short", YT)),
        ("https://youtube.com/shorts/abcdefghijk?feature=share", ("youtube", "abcdefghijk", "short", YT)),
        ("  youtube.com/shorts/abcdefghijk  ", ("youtube", "abcdefghijk", "short", YT)),
        ("https://m.youtube.com/watch?v=abcdefghijk&t=10s", ("youtube", "abcdefghijk", "watch", YT)),
        ("https://youtu.be/abcdefghijk?si=XYZ", ("youtube", "abcdefghijk", "watch", YT)),
        ("https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=abc", ("instagram", "C1a2B3c4D5e", "reel", IG_REEL)),
        ("https://instagram.com/reels/C1a2B3c4D5e", ("instagram", "C1a2B3c4D5e", "reel", IG_REEL)),
        ("https://www.instagram.com/birhesap/reel/C1a2B3c4D5e/", ("instagram", "C1a2B3c4D5e", "reel", IG_REEL)),
        ("https://www.instagram.com/p/C1a2B3c4D5e/", ("instagram", "C1a2B3c4D5e", "post", IG_POST)),
    ],
)
def test_link_varyantlari(girdi, beklenen):
    p = parse_link(girdi)
    assert (p.platform, p.platform_id, p.kind, p.canonical_url) == beklenen


@pytest.mark.parametrize(
    "girdi",
    [
        "",
        "https://vimeo.com/123",
        "https://www.youtube.com/watch?v=kisa",
        "https://www.instagram.com/birhesap/",
        "ftp://youtube.com/shorts/abcdefghijk",
    ],
)
def test_gecersiz_linkler(girdi):
    with pytest.raises(SourceError) as e:
        parse_link(girdi)
    assert e.value.code == "LINK_GECERSIZ"


# --- İL §6.7 link kuralları (Task A1) ---
def _kod(girdi):
    with pytest.raises(SourceError) as e:
        parse_link(girdi)
    return e.value


@pytest.mark.parametrize("girdi", ["https://www.instagram.com/reel/-----/", "https://www.instagram.com/reel/_____/"])
def test_parse_yalniz_tire_kod_reddedilir(girdi):
    assert _kod(girdi).code == "LINK_GECERSIZ"


@pytest.mark.parametrize(
    "girdi", ["https://a@instagram.com/reel/ABCDE12/", "https://www.instagram.com:8080/reel/ABCDE12/"]
)
def test_parse_kullanici_bilgisi_ve_port_reddedilir(girdi):
    assert _kod(girdi).code == "LINK_GECERSIZ"


def test_parse_443_portu_kabul():
    assert parse_link("https://www.instagram.com:443/reel/ABCDE12/").platform_id == "ABCDE12"


def test_parse_karisik_tire_kod_kabul():
    assert parse_link("https://www.instagram.com/reel/-a_b-/").platform_id == "-a_b-"


def test_parse_tv_reddedilir():
    assert _kod("https://www.instagram.com/tv/ABCDE12/").code == "LINK_GECERSIZ"


def test_parse_gecersiz_mesaj():
    e = _kod("https://example.com/x")
    assert e.message == (
        "Bu link tanınmadı. YouTube Shorts ya da Instagram Reel linki girin ya da videoyu dosya olarak yükleyin."
    )
