"""Draw a branded gift card PDF with reportlab.

The page is A6 landscape (148 x 105 mm): it reads well on a phone screen and
prints cleanly. All layout measurements live in :class:`_Layout`, so the design
can be adjusted in one place.
"""

import io
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A6, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from gavekort import qr
from gavekort.config import Brand, CardSpec

PAGE_SIZE: tuple[float, float] = landscape(A6)


@dataclass(frozen=True, slots=True)
class _Layout:
    """Layout measurements in points (multiply mm values by ``mm``)."""

    margin: float = 10 * mm
    logo_max_width: float = 42 * mm
    logo_max_height: float = 18 * mm
    qr_size: float = 46 * mm
    qr_tile_padding: float = 3 * mm
    qr_tile_radius: float = 3 * mm
    eyebrow_size: float = 9
    title_size: float = 20
    code_size: float = 10
    footer_size: float = 7.5


_LAYOUT = _Layout()


@dataclass(frozen=True, slots=True)
class _Fonts:
    regular: str
    bold: str
    code: str
    code_spacing: float
    """Extra space between characters of the card code, in points."""


def render_card(spec: CardSpec, brand: Brand, code: str, url: str, validity_text: str) -> bytes:
    """Render one gift card and return the PDF as bytes.

    Args:
        spec: Card type and title, e.g. "60 minutter massasje".
        brand: Colors, logo, fonts and booking link.
        code: The human-readable card code, printed under the QR.
        url: The URL the QR code encodes.
        validity_text: Line printed in the footer, e.g. "Gyldig i 12 måneder fra kjøpsdato".
    """
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = Canvas(buffer, pagesize=PAGE_SIZE, pageCompression=1)
    c.setTitle(f"Gavekort {spec.title} – {code}")
    c.setAuthor(brand.business_name)

    fonts = _register_fonts(brand)
    text_color = HexColor(brand.text_color)
    lay = _LAYOUT

    c.setFillColor(HexColor(brand.background_color))
    c.rect(0, 0, width, height, stroke=0, fill=1)

    # QR tile, vertically centred on the right.
    tile_size = lay.qr_size + 2 * lay.qr_tile_padding
    tile_x = width - lay.margin - tile_size
    tile_y = (height - tile_size) / 2 + 3 * mm
    c.setFillColor(white)
    c.roundRect(tile_x, tile_y, tile_size, tile_size, lay.qr_tile_radius, stroke=0, fill=1)
    _draw_qr(c, url, tile_x + lay.qr_tile_padding, tile_y + lay.qr_tile_padding, lay.qr_size)

    c.setFillColor(text_color)
    c.setFont(fonts.code, lay.code_size)
    code_width = pdfmetrics.stringWidth(code, fonts.code, lay.code_size)
    code_width += fonts.code_spacing * (len(code) - 1)
    c.drawString(
        tile_x + (tile_size - code_width) / 2,
        tile_y - 5 * mm,
        code,
        charSpace=fonts.code_spacing,
    )

    # Left column: logo, eyebrow, title.
    left = lay.margin
    column_width = tile_x - left - 6 * mm
    top = height - lay.margin
    if brand.logo is not None:
        logo_height = _draw_logo(c, brand.logo, left, top)
        top -= logo_height + 7 * mm
    else:
        top -= 8 * mm

    c.setFillColor(text_color)
    c.setFont(fonts.bold, lay.eyebrow_size)
    c.drawString(left, top - lay.eyebrow_size, _spaced("GAVEKORT"))
    top -= lay.eyebrow_size + 5 * mm

    c.setFillColor(text_color)
    for line in _wrap(spec.title, fonts.bold, lay.title_size, column_width):
        c.setFont(fonts.bold, lay.title_size)
        c.drawString(left, top - lay.title_size, line)
        top -= lay.title_size * 1.2

    # Footer: validity and clickable booking link.
    footer_y = lay.margin
    c.setFillColor(text_color)
    c.setFont(fonts.regular, lay.footer_size)
    c.drawString(left, footer_y + lay.footer_size * 1.6, validity_text)
    booking_text = brand.booking_text
    c.setFillColor(text_color)
    c.drawString(left, footer_y, booking_text)
    text_width = pdfmetrics.stringWidth(booking_text, fonts.regular, lay.footer_size)
    c.linkURL(
        brand.booking_url,
        (left, footer_y - 1, left + text_width, footer_y + lay.footer_size),
        relative=0,
    )

    c.showPage()
    c.save()
    return buffer.getvalue()


def _draw_qr(c: Canvas, url: str, x: float, y: float, size: float) -> None:
    """Draw the QR for ``url`` as vector squares inside the given box.

    The white tile behind it provides contrast; the quiet zone is kept by
    shrinking the code to leave ``QUIET_ZONE`` modules free on every side.
    """
    code = qr.make(url)
    modules, _ = code.symbol_size(border=qr.QUIET_ZONE)
    module = size / modules
    origin_x = x + qr.QUIET_ZONE * module
    origin_top = y + size - qr.QUIET_ZONE * module
    c.setFillColor(Color(0, 0, 0))
    path = c.beginPath()
    for col, row in qr.dark_modules(code):
        # Slight overlap avoids hairline gaps between adjacent squares in some viewers.
        path.rect(
            origin_x + col * module, origin_top - (row + 1) * module, module + 0.01, module + 0.01
        )
    c.drawPath(path, stroke=0, fill=1)


def _draw_logo(c: Canvas, logo: Path, x: float, top: float) -> float:
    """Draw the logo with its top-left at ``(x, top)`` and return its height."""
    image = ImageReader(str(logo))
    img_width, img_height = image.getSize()
    scale = min(_LAYOUT.logo_max_width / img_width, _LAYOUT.logo_max_height / img_height)
    width, height = img_width * scale, img_height * scale
    c.drawImage(image, x, top - height, width, height, mask="auto")
    return height


def _register_fonts(brand: Brand) -> _Fonts:
    """Register custom TTF fonts if configured, falling back to Helvetica.

    The card code uses the bold brand font when one is configured (the code
    alphabet has no look-alike characters), otherwise monospaced Courier.
    """
    regular, bold = "Helvetica", "Helvetica-Bold"
    if brand.font_regular is not None:
        regular = _register_ttf(brand.font_regular)
    if brand.font_bold is not None:
        bold = _register_ttf(brand.font_bold)
    elif brand.font_regular is not None:
        bold = regular
    if brand.font_bold is None and brand.font_regular is None:
        return _Fonts(regular=regular, bold=bold, code="Courier-Bold", code_spacing=0)
    return _Fonts(regular=regular, bold=bold, code=bold, code_spacing=1)


def _register_ttf(path: Path) -> str:
    name = path.stem
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    return name


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    """Greedily wrap ``text`` into lines no wider than ``max_width``."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and pdfmetrics.stringWidth(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _spaced(text: str) -> str:
    """Letter-space a short uppercase label, e.g. ``G A V E K O R T``."""
    return " ".join(text)
