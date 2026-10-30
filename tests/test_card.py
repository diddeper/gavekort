import dataclasses
import io
from pathlib import Path
from typing import cast

import pytest
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject
from reportlab.lib.units import mm

from gavekort.card import PAGE_SIZE, render_card
from gavekort.config import CardType, Config
from tests.conftest import BOOKING_URL

FONTS = Path(__file__).parent.parent / "assets" / "fonts"


def _render(cfg: Config) -> PdfReader:
    pdf = render_card(
        cfg.cards[CardType.MIN_60],
        cfg.brand,
        "GK-ABCD-EFGH",
        "https://x.test/exec?kode=GK-ABCD-EFGH",
        cfg.validity_text,
    )
    return PdfReader(io.BytesIO(pdf))


def test_single_page_148mm_wide_with_card_proportions(cfg: Config) -> None:
    reader = _render(cfg)
    assert len(reader.pages) == 1
    box = reader.pages[0].mediabox
    assert round(float(box.width)) == round(148 * mm)
    assert (round(float(box.width)), round(float(box.height))) == tuple(map(round, PAGE_SIZE))
    assert float(box.width) / float(box.height) == pytest.approx(1012 / 638)


def test_contains_name_and_validity_but_not_code_or_title(cfg: Config) -> None:
    # Compare without spaces: letter spacing may split words in the extracted text.
    text = "".join(_render(cfg).pages[0].extract_text().split())
    assert "TestTestesen" in text
    assert "Gyldigi12månederfrakjøpsdato" in text
    # Code and treatment are tracked in the sheet, not printed on the card.
    assert "GK-ABCD-EFGH" not in text
    assert "minutter" not in text


def test_booking_link_is_clickable(cfg: Config) -> None:
    page = _render(cfg).pages[0]
    annotations = cast(ArrayObject, page["/Annots"])
    uris = [
        str(cast(DictionaryObject, cast(DictionaryObject, a.get_object())["/A"])["/URI"])
        for a in annotations
    ]
    assert BOOKING_URL in uris


def test_embeds_configured_brand_font(cfg: Config) -> None:
    brand = dataclasses.replace(
        cfg.brand,
        font_light=FONTS / "Montserrat-Light.ttf",
        font_regular=FONTS / "Montserrat-Regular.ttf",
        font_bold=FONTS / "Montserrat-Medium.ttf",
    )
    cfg = dataclasses.replace(cfg, brand=brand)
    page = _render(cfg).pages[0]
    resources = cast(DictionaryObject, page["/Resources"])
    fonts = cast(DictionaryObject, resources["/Font"])
    base_fonts = {str(cast(DictionaryObject, f.get_object())["/BaseFont"]) for f in fonts.values()}
    assert any("Montserrat-Regular" in name for name in base_fonts)
    assert any("Montserrat-Light" in name for name in base_fonts)
    assert any("Montserrat-Medium" in name for name in base_fonts)
    assert "GAVEKORT" in "".join(page.extract_text().split())


def test_rejects_mark_with_curves(cfg: Config, tmp_path: Path) -> None:
    mark = tmp_path / "curvy.svg"
    mark.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<path d="M0 0C1 1 2 2 3 3Z"/></svg>',
        encoding="utf-8",
    )
    cfg = dataclasses.replace(cfg, brand=dataclasses.replace(cfg.brand, mark=mark))
    with pytest.raises(ValueError, match="path commands"):
        _render(cfg)
