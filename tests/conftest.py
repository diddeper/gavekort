"""Shared fixtures: a minimal, valid config in a temporary directory."""

from pathlib import Path

import pytest

from gavekort.config import Config, load

WEB_APP_URL = "https://script.google.com/macros/s/TEST/exec"
BOOKING_URL = "https://example.com/booking"

MARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    '<path d="M0 0L10 0L10 10L0 10ZM2 2H8V8H2Z"/></svg>'
)

CONFIG_TEMPLATE = """
web_app_url = "{web_app_url}"
validity_text = "Gyldig i 12 måneder fra kjøpsdato"

[brand]
business_name = "Test Massasje"
name = "Test Testesen"
tagline = "Massasjeterapeut"
background_color = "#F3EDE6"
text_color = "#3B2F2A"
mark = "mark.svg"
booking_url = "{booking_url}"
scan_text = "Skannes ved oppmøte"

[cards.60]
title = "60 minutter massasje"

[cards.90]
title = "90 minutter massasje"
"""


def write_config(directory: Path, **overrides: str) -> Path:
    """Write a test config (and mark) to ``directory`` and return the config path."""
    (directory / "mark.svg").write_text(MARK_SVG, encoding="utf-8")
    values = {"web_app_url": WEB_APP_URL, "booking_url": BOOKING_URL} | overrides
    path = directory / "config.toml"
    path.write_text(CONFIG_TEMPLATE.format(**values), encoding="utf-8")
    return path


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    """A loaded config whose output directory is inside ``tmp_path``."""
    return load(write_config(tmp_path))
