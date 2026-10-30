"""Draw a branded gift card PDF with reportlab.

The layout follows design "1c alt 3" (``Gavekort.dc.html`` in Claude Design):
"GAVEKORT" with the validity line opposite it, name and tagline top left, a large
QR above the booking link bottom left, and the hands mark bleeding off the
bottom-right corner. The design is drawn on a 1012 x 638
px canvas; :class:`_Layout` keeps its measurements in those pixels and
:func:`_px` scales them to the 148 mm wide page, so values can be copied
straight from the design.
"""

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from gavekort import qr
from gavekort.config import Brand, CardSpec

_DESIGN_WIDTH = 1012
_DESIGN_HEIGHT = 638
_PAGE_WIDTH = 148 * mm

PAGE_SIZE: tuple[float, float] = (_PAGE_WIDTH, _PAGE_WIDTH * _DESIGN_HEIGHT / _DESIGN_WIDTH)
"""148 x 93.3 mm: A6 width with the design's credit-card proportions."""

# Montserrat's vertical metrics (per 1 em), used to place baselines like a browser does.
_ASCENT = 0.968
_DESCENT = 0.251

_FILL_EVEN_ODD = 0
"""reportlab's even-odd fill mode (``canvas.FILL_EVEN_ODD``, missing from the type stubs)."""


def _px(value: float) -> float:
    """Convert design pixels to PDF points."""
    return value * _PAGE_WIDTH / _DESIGN_WIDTH


@dataclass(frozen=True, slots=True)
class _Text:
    """A text style: size in design px, letter spacing in em."""

    size: float
    tracking: float = 0.0
    line_height: float = _ASCENT + _DESCENT


@dataclass(frozen=True, slots=True)
class _Layout:
    """Layout measurements in design pixels (see :func:`_px`)."""

    pad_x: float = 68
    pad_y: float = 60
    eyebrow: _Text = _Text(20, 0.28, 1)
    validity: _Text = _Text(12, 0.06, 1)
    eyebrow_bottom: float = 14
    top_gap: float = 12
    name: _Text = _Text(52, 0.08, 1.05)
    name_gap: float = 10
    tagline: _Text = _Text(16, 0.26)
    qr_size: float = 220
    qr_link_gap: float = 16
    link: _Text = _Text(14, 0.18)
    link_underline_gap: float = 4
    mark_height: float = 520
    mark_right: float = -110
    mark_bottom: float = -60
    mark_opacity: float = 0.9


_LAYOUT = _Layout()


@dataclass(frozen=True, slots=True)
class _Fonts:
    light: str
    regular: str
    bold: str


@dataclass(frozen=True, slots=True)
class _Mark:
    width: float
    height: float
    subpaths: list[list[tuple[float, float]]]


def render_card(spec: CardSpec, brand: Brand, code: str, url: str, validity_text: str) -> bytes:
    """Render one gift card and return the PDF as bytes.

    Args:
        spec: Card type; its title is only used in the PDF metadata.
        brand: Colors, mark, names, fonts and booking link.
        code: The card code; only used in the PDF metadata (it is tracked in the sheet).
        url: The URL the QR code encodes.
        validity_text: Line printed top right, e.g. "Gyldig i 12 måneder fra kjøpsdato".
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

    # Drawn first so all text sits on top of it.
    if brand.mark is not None:
        c.saveState()
        c.setFillColor(text_color)
        c.setFillAlpha(lay.mark_opacity)
        _draw_mark(c, _load_mark(brand.mark))
        c.restoreState()

    c.setFillColor(text_color)
    left = lay.pad_x
    right = _DESIGN_WIDTH - lay.pad_x

    # Top row: eyebrow left, validity right on the same baseline.
    top = lay.pad_y
    _draw_text(c, "GAVEKORT", fonts.bold, lay.eyebrow, left, top)
    validity_top = top + _baseline(lay.eyebrow) - _baseline(lay.validity)
    validity_width = _text_width(validity_text, fonts.regular, lay.validity)
    _draw_text(c, validity_text, fonts.regular, lay.validity, right - validity_width, validity_top)
    top += _line_height(lay.eyebrow) + lay.eyebrow_bottom + lay.top_gap

    # Name and tagline.
    if brand.name:
        _draw_text(c, brand.name, fonts.light, lay.name, left, top)
        top += _line_height(lay.name) + lay.name_gap
    if brand.tagline:
        _draw_text(c, brand.tagline.upper(), fonts.regular, lay.tagline, left, top)

    # Bottom block: QR centred above the underlined booking link, bottom-aligned.
    booking_text = brand.booking_text.upper()
    link_width = _text_width(booking_text, fonts.bold, lay.link)
    column_width = max(lay.qr_size, link_width)
    underline_y = _DESIGN_HEIGHT - lay.pad_y - 0.5
    link_top = underline_y - 0.5 - lay.link_underline_gap - _line_height(lay.link)
    link_left = left + (column_width - link_width) / 2
    qr_top = link_top - lay.qr_link_gap - lay.qr_size
    _draw_qr(c, url, left + (column_width - lay.qr_size) / 2, qr_top, lay.qr_size)

    _draw_text(c, booking_text, fonts.bold, lay.link, link_left, link_top)
    c.setStrokeColor(text_color)
    c.setLineWidth(_px(1))
    c.line(
        _px(link_left),
        height - _px(underline_y),
        _px(link_left + link_width),
        height - _px(underline_y),
    )
    c.linkURL(
        brand.booking_url,
        (
            _px(link_left),
            height - _px(underline_y + 1),
            _px(link_left + link_width),
            height - _px(link_top),
        ),
        relative=0,
    )

    c.showPage()
    c.save()
    return buffer.getvalue()


def _line_height(style: _Text) -> float:
    return style.size * style.line_height


def _baseline(style: _Text) -> float:
    """Distance from the top of a CSS line box to its baseline, in design px."""
    half_leading = (_line_height(style) - style.size * (_ASCENT + _DESCENT)) / 2
    return half_leading + style.size * _ASCENT


def _text_width(text: str, font: str, style: _Text) -> float:
    """Width in design px, including the trailing letter spacing (as CSS does)."""
    width = pdfmetrics.stringWidth(text, font, style.size)
    return width + style.size * style.tracking * len(text)


def _draw_text(c: Canvas, text: str, font: str, style: _Text, x: float, top: float) -> None:
    """Draw one line whose CSS line box starts at design coordinates ``(x, top)``."""
    baseline = top + _baseline(style)
    c.setFont(font, _px(style.size))
    c.drawString(
        _px(x), PAGE_SIZE[1] - _px(baseline), text, charSpace=_px(style.size * style.tracking)
    )


def _draw_qr(c: Canvas, url: str, x: float, top: float, size: float) -> None:
    """Draw the QR for ``url`` as vector squares filling a ``size`` px box at ``(x, top)``.

    Only the modules are drawn, directly on the card background. The quiet zone
    is the empty background around the box, which the layout keeps clear.
    """
    code = qr.make(url)
    modules, _ = code.symbol_size(border=0)
    module = _px(size) / modules
    origin_x = _px(x)
    origin_top = PAGE_SIZE[1] - _px(top)
    path = c.beginPath()
    for col, row in qr.dark_modules(code):
        # Slight overlap avoids hairline gaps between adjacent squares in some viewers.
        path.rect(
            origin_x + col * module, origin_top - (row + 1) * module, module + 0.01, module + 0.01
        )
    c.drawPath(path, stroke=0, fill=1)


def _draw_mark(c: Canvas, mark: _Mark) -> None:
    """Draw the mark scaled to ``mark_height``, offset from the bottom-right corner."""
    lay = _LAYOUT
    scale = _px(lay.mark_height) / mark.height
    right = PAGE_SIZE[0] - _px(lay.mark_right)
    bottom = _px(lay.mark_bottom)
    left = right - mark.width * scale
    top = bottom + mark.height * scale
    path = c.beginPath()
    for points in mark.subpaths:
        (x0, y0), *rest = points
        path.moveTo(left + x0 * scale, top - y0 * scale)
        for x, y in rest:
            path.lineTo(left + x * scale, top - y * scale)
        path.close()
    c.drawPath(path, stroke=0, fill=1, fillMode=_FILL_EVEN_ODD)


_PATH_TOKEN = re.compile(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _load_mark(path: Path) -> _Mark:
    """Read a single-color SVG made of straight-line paths (M, L, H, V, Z).

    Raises:
        ValueError: If the SVG has no viewBox or uses other path commands.
    """
    root = ET.parse(path).getroot()
    view_box = root.get("viewBox")
    if view_box is None:
        raise ValueError(f"{path} has no viewBox")
    _, _, width, height = (float(v) for v in view_box.replace(",", " ").split())

    subpaths: list[list[tuple[float, float]]] = []
    for element in root.iter("{http://www.w3.org/2000/svg}path"):
        tokens = _PATH_TOKEN.findall(element.get("d", ""))
        x = y = 0.0
        command = ""
        i = 0
        while i < len(tokens):
            if tokens[i].isalpha():
                command = tokens[i]
                i += 1
                if command == "Z":
                    command = ""
                continue
            match command:
                case "M":
                    x, y = float(tokens[i]), float(tokens[i + 1])
                    subpaths.append([(x, y)])
                    command, i = "L", i + 2
                    continue
                case "L":
                    x, y = float(tokens[i]), float(tokens[i + 1])
                    i += 2
                case "H":
                    x = float(tokens[i])
                    i += 1
                case "V":
                    y = float(tokens[i])
                    i += 1
                case _:
                    raise ValueError(
                        f"{path}: only absolute M, L, H, V and Z path commands are supported, "
                        f"found {command or tokens[i]!r}"
                    )
            subpaths[-1].append((x, y))
    return _Mark(width=width, height=height, subpaths=subpaths)


def _register_fonts(brand: Brand) -> _Fonts:
    """Register custom TTF fonts if configured, falling back to Helvetica.

    A missing light or bold font falls back to the regular one.
    """
    if brand.font_regular is None:
        return _Fonts(light="Helvetica", regular="Helvetica", bold="Helvetica-Bold")
    regular = _register_ttf(brand.font_regular)
    light = _register_ttf(brand.font_light) if brand.font_light is not None else regular
    bold = _register_ttf(brand.font_bold) if brand.font_bold is not None else regular
    return _Fonts(light=light, regular=regular, bold=bold)


def _register_ttf(path: Path) -> str:
    name = path.stem
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    return name
