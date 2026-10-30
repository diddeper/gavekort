"""The single source of QR codes for both PDFs and image files.

Keeping generation in one place guarantees that the QR printed on a physical
card and the one embedded in a PDF encode exactly the same URL.
"""

import io
from pathlib import Path
from urllib.parse import urlencode

import segno
from PIL import Image, ImageDraw, ImageFont

QUIET_ZONE = 4
"""Border in modules around the code; 4 is what the QR standard requires."""

CODE_PARAM = "kode"
"""URL parameter carrying the card code.

Must not be ``c`` or ``sid``: Apps Script reserves those names, and using them
makes Google answer with "unable to open the file" instead of serving the page.
"""

_DARK = "#000000"
_LIGHT = "#FFFFFF"


def card_url(base_url: str, code: str) -> str:
    """Return the URL a card's QR code points to: ``<base_url>?kode=<code>``."""
    return f"{base_url}?{urlencode({CODE_PARAM: code})}"


def make(url: str) -> segno.QRCode:
    """Return a QR code for ``url`` with error-correction level M (~15%)."""
    return segno.make(url, error="m", micro=False)


def dark_modules(qr: segno.QRCode) -> list[tuple[int, int]]:
    """Return the ``(column, row)`` of each dark module, without quiet zone.

    Row 0 is the top row. Used by the PDF renderer to draw the code as vectors.
    """
    return [(x, y) for y, row in enumerate(qr.matrix) for x, bit in enumerate(row) if bit]


def save_png(qr: segno.QRCode, path: Path, *, scale: int = 20, label: str | None = None) -> None:
    """Write ``qr`` as a black-on-white PNG.

    Args:
        qr: The code to write.
        path: Destination file.
        scale: Pixels per module. The default gives roughly 600-700 px.
        label: Optional text (the card code) printed under the QR as a fallback.
    """
    if label is None:
        qr.save(str(path), kind="png", scale=scale, border=QUIET_ZONE, dark=_DARK, light=_LIGHT)
        return

    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=scale, border=QUIET_ZONE, dark=_DARK, light=_LIGHT)
    buffer.seek(0)
    with Image.open(buffer) as image:
        code_image = image.convert("RGB")
    font = ImageFont.load_default(size=scale * 2)
    label_height = scale * 4
    canvas = Image.new("RGB", (code_image.width, code_image.height + label_height), _LIGHT)
    canvas.paste(code_image, (0, 0))
    ImageDraw.Draw(canvas).text(
        (canvas.width / 2, code_image.height + label_height / 4),
        label,
        fill=_DARK,
        font=font,
        anchor="mt",
    )
    canvas.save(path, format="PNG")


def save_svg(qr: segno.QRCode, path: Path, *, label: str | None = None) -> None:
    """Write ``qr`` as a scalable SVG, in mm units, for print.

    Args:
        qr: The code to write.
        path: Destination file.
        label: Optional text (the card code) printed under the QR as a fallback.
    """
    if label is None:
        qr.save(str(path), kind="svg", border=QUIET_ZONE, dark=_DARK, light=_LIGHT, unit="mm")
        return

    size, _ = qr.symbol_size(border=QUIET_ZONE)
    label_height = 4
    # svg_inline() yields an <svg> sized in user units (1 unit = 1 module).
    inner = qr.svg_inline(border=QUIET_ZONE, dark=_DARK, light=_LIGHT)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size + label_height}" '
        f'width="{size}mm" height="{size + label_height}mm">'
        f'<rect width="100%" height="100%" fill="{_LIGHT}"/>'
        f"{inner}"
        f'<text x="{size / 2}" y="{size + label_height / 2}" text-anchor="middle" '
        f'dominant-baseline="middle" font-family="Menlo, Consolas, monospace" '
        f'font-size="2" letter-spacing="0.2" fill="{_DARK}">{label}</text>'
        "</svg>"
    )
    path.write_text(svg, encoding="utf-8")
