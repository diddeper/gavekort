from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import segno
from PIL import Image

from gavekort import qr

URL = "https://script.google.com/macros/s/TEST/exec?kode=GK-ABCD-EFGH"


def test_card_url_appends_code() -> None:
    assert (
        qr.card_url("https://x.test/exec", "GK-ABCD-EFGH")
        == "https://x.test/exec?kode=GK-ABCD-EFGH"
    )


def test_card_url_avoids_parameters_reserved_by_apps_script() -> None:
    query = parse_qs(urlsplit(qr.card_url("https://x.test/exec", "GK-ABCD-EFGH")).query)
    assert not {"c", "sid"} & query.keys()
    assert query[qr.CODE_PARAM] == ["GK-ABCD-EFGH"]


def test_png_is_large_enough_for_print(tmp_path: Path) -> None:
    path = tmp_path / "code.png"
    qr.save_png(qr.make(URL), path)
    assert path.read_bytes().startswith(b"\x89PNG")
    with Image.open(path) as image:
        assert image.width == image.height >= 600


def test_png_label_adds_space_below(tmp_path: Path) -> None:
    plain, labelled = tmp_path / "plain.png", tmp_path / "label.png"
    symbol = qr.make(URL)
    qr.save_png(symbol, plain)
    qr.save_png(symbol, labelled, label="GK-ABCD-EFGH")
    with Image.open(plain) as a, Image.open(labelled) as b:
        assert b.width == a.width
        assert b.height > a.height


def test_svg_matches_segno_output(tmp_path: Path) -> None:
    path = tmp_path / "code.svg"
    qr.save_svg(qr.make(URL), path)
    expected = segno.make(URL, error="m").svg_inline(border=qr.QUIET_ZONE)
    path_data = expected.split(' d="')[1].split('"')[0]
    assert path_data in path.read_text(encoding="utf-8")


def test_svg_label_contains_code(tmp_path: Path) -> None:
    path = tmp_path / "code.svg"
    qr.save_svg(qr.make(URL), path, label="GK-ABCD-EFGH")
    assert ">GK-ABCD-EFGH</text>" in path.read_text(encoding="utf-8")
