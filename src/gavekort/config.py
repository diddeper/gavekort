"""Load and validate ``config.toml``.

The TOML file is parsed into frozen dataclasses so the rest of the code works
with typed, validated values. Every problem is reported through
:class:`ConfigError` with a message that says what to fix.
"""

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ConfigError(Exception):
    """Raised when ``config.toml`` is missing, malformed or incomplete."""


class CardType(StrEnum):
    """Treatment a gift card is valid for."""

    MIN_60 = "60"
    MIN_90 = "90"


@dataclass(frozen=True, slots=True)
class Brand:
    """Visual identity shared by all cards."""

    business_name: str
    background_color: str
    text_color: str
    logo: Path | None
    booking_url: str
    booking_text: str
    """Footer line shown on the card; clicking it opens ``booking_url``."""
    font_regular: Path | None
    font_bold: Path | None


@dataclass(frozen=True, slots=True)
class CardSpec:
    """Per-type card content."""

    card_type: CardType
    title: str


@dataclass(frozen=True, slots=True)
class Config:
    """Complete, validated configuration."""

    web_app_url: str
    validity_text: str
    brand: Brand
    cards: Mapping[CardType, CardSpec]
    output_dir: Path

    def require_web_app_url(self) -> str:
        """Return the web app URL, or fail if it has not been set yet.

        Raises:
            ConfigError: If ``web_app_url`` is blank, since every QR code would be dead.
        """
        if not self.web_app_url:
            raise ConfigError(
                "web_app_url is empty in config.toml. Deploy the Apps Script web app first "
                "and paste its /exec URL, otherwise the QR codes lead nowhere."
            )
        return self.web_app_url


def load(path: Path) -> Config:
    """Read and validate the configuration file at ``path``.

    Relative file paths in the config (logo, fonts) are resolved against the
    directory that contains the config file.

    Raises:
        ConfigError: If the file is missing or any value is invalid.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"Config file not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} is not valid TOML: {e}") from e

    base = path.parent
    web_app_url = _str(raw, "web_app_url", required=False)
    if web_app_url:
        _require_https(web_app_url, "web_app_url")

    return Config(
        web_app_url=web_app_url,
        validity_text=_str(raw, "validity_text"),
        brand=_parse_brand(_table(raw, "brand"), base),
        cards=_parse_cards(_table(raw, "cards")),
        output_dir=base / (_str(raw, "output_dir", required=False) or "output"),
    )


def _parse_brand(table: Mapping[str, object], base: Path) -> Brand:
    booking_url = _str(table, "booking_url")
    _require_https(booking_url, "brand.booking_url")
    return Brand(
        business_name=_str(table, "business_name"),
        background_color=_color(table, "background_color"),
        text_color=_color(table, "text_color"),
        logo=_file(table, "logo", base),
        booking_url=booking_url,
        booking_text=_str(table, "booking_text", required=False)
        or f"Bestill time: {_display_url(booking_url)}",
        font_regular=_file(table, "font_regular", base),
        font_bold=_file(table, "font_bold", base),
    )


def _parse_cards(table: Mapping[str, object]) -> dict[CardType, CardSpec]:
    cards: dict[CardType, CardSpec] = {}
    for card_type in CardType:
        section = _table(table, card_type.value, prefix="cards.")
        cards[card_type] = CardSpec(card_type=card_type, title=_str(section, "title"))
    return cards


def _table(raw: Mapping[str, object], key: str, *, prefix: str = "") -> Mapping[str, object]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing section [{prefix}{key}] in config.toml")
    return {str(k): v for k, v in value.items()}


def _str(raw: Mapping[str, object], key: str, *, required: bool = True) -> str:
    value = raw.get(key, "")
    if not isinstance(value, str):
        raise ConfigError(f"'{key}' must be a string")
    value = value.strip()
    if required and not value:
        raise ConfigError(f"'{key}' is required in config.toml")
    return value


def _color(raw: Mapping[str, object], key: str) -> str:
    value = _str(raw, key)
    if not _HEX_COLOR.match(value):
        raise ConfigError(f"'{key}' must be a hex color like #A67C6D, got {value!r}")
    return value


def _file(raw: Mapping[str, object], key: str, base: Path) -> Path | None:
    value = _str(raw, key, required=False)
    if not value:
        return None
    path = (base / value).resolve()
    if not path.is_file():
        raise ConfigError(f"'{key}' points to a file that does not exist: {path}")
    return path


def _display_url(url: str) -> str:
    """Shorten a URL for print: no scheme, ``www.``, query, fragment or trailing slash."""
    bare = url.removeprefix("https://").removeprefix("www.")
    return bare.split("#", 1)[0].split("?", 1)[0].rstrip("/")


def _require_https(url: str, key: str) -> None:
    if not url.startswith("https://"):
        raise ConfigError(f"'{key}' must start with https://, got {url!r}")
