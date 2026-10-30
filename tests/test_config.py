from pathlib import Path

import pytest

from gavekort.config import CardType, ConfigError, load
from tests.conftest import write_config


def test_loads_valid_config(tmp_path: Path) -> None:
    cfg = load(write_config(tmp_path))
    assert cfg.brand.mark == (tmp_path / "mark.svg").resolve()
    assert cfg.brand.name == "Test Testesen"
    assert cfg.cards[CardType.MIN_90].title == "90 minutter massasje"
    assert cfg.output_dir == tmp_path / "output"


def test_booking_text_defaults_to_short_url(tmp_path: Path) -> None:
    url = "https://www.example.com/book/x/?ref=1#choose-service"
    cfg = load(write_config(tmp_path, booking_url=url))
    assert cfg.brand.booking_text == "Bestill time: example.com/book/x"
    assert cfg.brand.booking_url == url


def test_rejects_bad_color(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    path.write_text(path.read_text().replace("#F3EDE6", "beige"))
    with pytest.raises(ConfigError, match="background_color"):
        load(path)


def test_rejects_missing_mark(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    (tmp_path / "mark.svg").unlink()
    with pytest.raises(ConfigError, match="mark"):
        load(path)


def test_rejects_non_https_urls(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="booking_url"):
        load(write_config(tmp_path, booking_url="http://example.com"))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load(tmp_path / "nope.toml")
