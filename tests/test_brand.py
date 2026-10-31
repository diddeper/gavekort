"""Keep the scan page (apps_script/Side.html) on brand with the PDF card.

Colours come from config.toml; text styles and gaps from ``LAYOUT`` in card.py;
font weights from the configured Montserrat files.
"""

import re
from pathlib import Path

import pytest

from gavekort.card import LAYOUT
from gavekort.config import load

ROOT = Path(__file__).parent.parent
HTML = (ROOT / "apps_script" / "Side.html").read_text(encoding="utf-8")

TEXT_STYLES = ["eyebrow", "validity", "name", "tagline", "link"]
GAPS = [
    "eyebrow_bottom",
    "eyebrow_divider_gap",
    "top_gap",
    "name_gap",
    "link_gap",
    "link_underline_gap",
]
WEIGHTS = {
    "light": ("font_light", 300),
    "regular": ("font_regular", 400),
    "medium": ("font_bold", 500),
}
WEIGHT_NAMES = {300: "Light", 400: "Regular", 500: "Medium"}


def _css_var(name: str) -> str:
    match = re.search(rf"--{name}:\s*([^;]+);", HTML)
    assert match, f"--{name} not found in Side.html"
    return match.group(1).strip()


def _number(value: str, unit: str = "") -> float:
    assert value.endswith(unit), f"expected a value in {unit or 'plain numbers'}, got {value!r}"
    return float(value.removesuffix(unit))


def test_scan_page_uses_config_colors() -> None:
    brand = load(ROOT / "config.toml").brand
    assert _css_var("bg").lower() == brand.background_color.lower()
    assert _css_var("text").lower() == brand.text_color.lower()


@pytest.mark.parametrize("style", TEXT_STYLES)
def test_scan_page_text_styles_match_card(style: str) -> None:
    css = style.replace("_", "-")
    expected = getattr(LAYOUT, style)
    assert _number(_css_var(f"{css}-size"), "px") == expected.size
    assert _number(_css_var(f"{css}-tracking"), "em") == pytest.approx(expected.tracking)


@pytest.mark.parametrize("gap", GAPS)
def test_scan_page_gaps_match_card(gap: str) -> None:
    assert _number(_css_var(gap.replace("_", "-")), "px") == getattr(LAYOUT, gap)


@pytest.mark.parametrize("name", WEIGHTS)
def test_scan_page_weights_match_card_fonts(name: str) -> None:
    key, weight = WEIGHTS[name]
    font = getattr(load(ROOT / "config.toml").brand, key)
    assert font is not None and font.stem == f"Montserrat-{WEIGHT_NAMES[weight]}"
    assert _number(_css_var(name)) == weight


def test_scan_page_loads_only_the_card_weights() -> None:
    assert "family=Montserrat:wght@300;400;500&" in HTML
    literal_weights = set(re.findall(r"font-weight:\s*(\d+)", HTML))
    assert not literal_weights, f"use var(--light/--regular/--medium), found {literal_weights}"
