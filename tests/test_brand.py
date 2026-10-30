"""Keep the scan page (apps_script/Side.html) on brand with config.toml."""

import re
from pathlib import Path

from gavekort.config import load

ROOT = Path(__file__).parent.parent


def _css_var(html: str, name: str) -> str:
    match = re.search(rf"--{name}:\s*(#[0-9A-Fa-f]{{6}})", html)
    assert match, f"--{name} not found in Side.html"
    return match.group(1)


def test_scan_page_uses_config_colors() -> None:
    brand = load(ROOT / "config.toml").brand
    html = (ROOT / "apps_script" / "Side.html").read_text(encoding="utf-8")
    assert _css_var(html, "bg").lower() == brand.background_color.lower()
    assert _css_var(html, "text").lower() == brand.text_color.lower()
