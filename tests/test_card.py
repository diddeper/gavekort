import dataclasses
import io
from pathlib import Path
from typing import cast

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject
from reportlab.lib.pagesizes import A6, landscape

from gavekort.card import render_card
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


def test_single_a6_landscape_page(cfg: Config) -> None:
    reader = _render(cfg)
    assert len(reader.pages) == 1
    width, height = landscape(A6)
    box = reader.pages[0].mediabox
    assert (round(float(box.width)), round(float(box.height))) == (round(width), round(height))


def test_contains_code_title_and_validity(cfg: Config) -> None:
    # Normalise whitespace: the title may wrap over two lines.
    text = " ".join(_render(cfg).pages[0].extract_text().split())
    assert "GK-ABCD-EFGH" in text
    assert "60 minutter massasje" in text
    assert "Gyldig i 12 måneder fra kjøpsdato" in text


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
        font_regular=FONTS / "Montserrat-Regular.ttf",
        font_bold=FONTS / "Montserrat-SemiBold.ttf",
    )
    cfg = dataclasses.replace(cfg, brand=brand)
    page = _render(cfg).pages[0]
    resources = cast(DictionaryObject, page["/Resources"])
    fonts = cast(DictionaryObject, resources["/Font"])
    base_fonts = {str(cast(DictionaryObject, f.get_object())["/BaseFont"]) for f in fonts.values()}
    assert any("Montserrat-Regular" in name for name in base_fonts)
    assert any("Montserrat-SemiBold" in name for name in base_fonts)
    assert not any("Courier" in name for name in base_fonts)
    assert "GK-ABCD-EFGH" in page.extract_text()
