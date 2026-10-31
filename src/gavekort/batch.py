"""Generate a batch of gift cards: PDFs and/or QR images plus a CSV for the sheet.

Each batch is written to its own folder::

    output/2026-10-30_1312_60min/
        pdf/GK-7F3K-9QXA.pdf
        qr/GK-7F3K-9QXA.png
        qr/GK-7F3K-9QXA.svg
        batch.csv          <- overview with a header row, for reading
        import.csv         <- same rows without header: File > Import > Append in the sheet
"""

import csv
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from gavekort import codes, qr
from gavekort.card import render_card
from gavekort.config import CardType, Config


class OutputFormat(StrEnum):
    """File types a batch can produce."""

    PDF = "pdf"
    PNG = "png"
    SVG = "svg"


SHEET_COLUMNS = (
    "Kode",
    "Type",
    "Format",
    "Status",
    "Klipp",
    "Brukt",
    "Generert",
    "Aktivert",
    "Utløper",
    "Sist brukt",
)
"""Column headers, identical to the ``Gavekort`` sheet set up by ``setupSheet()``."""

STATUS_NOT_SOLD = "Ikke solgt"


@dataclass(frozen=True, slots=True)
class BatchResult:
    """What a call to :func:`generate` produced."""

    directory: Path
    codes: tuple[str, ...]
    csv_path: Path
    """``batch.csv``: the batch with a header row, for reading."""
    import_path: Path
    """``import.csv``: the same rows without a header, to append to the sheet."""


def generate(
    card_type: CardType,
    count: int,
    formats: Collection[OutputFormat],
    cfg: Config,
    *,
    clips: int = 1,
    label: bool = False,
    now: datetime | None = None,
) -> BatchResult:
    """Generate ``count`` new cards of ``card_type``.

    Args:
        card_type: 60 or 90 minutes.
        count: Number of cards, at least 1.
        formats: Which files to write per card. A PDF makes the card ``Digital``;
            QR images only make it ``Fysisk``.
        cfg: Loaded configuration.
        clips: Treatments per card. 1 is an ordinary card; more makes a
            clip card that stays ``Aktiv`` until every clip is used.
        label: Print the card code under the QR in PNG/SVG files.
        now: Timestamp for the batch (injectable for tests).

    Returns:
        The batch folder, the generated codes and the paths to ``batch.csv``
        and ``import.csv``.

    Raises:
        ValueError: If ``count`` or ``clips`` is below 1, or ``formats`` is empty.
        ConfigError: If the web app URL has not been configured.
    """
    if count < 1:
        raise ValueError("count must be at least 1")
    if clips < 1:
        raise ValueError("clips must be at least 1")
    if not formats:
        raise ValueError("at least one output format is required")
    base_url = cfg.require_web_app_url()
    now = now or datetime.now()

    directory = _new_batch_dir(cfg.output_dir, card_type, clips, now)
    batch_codes = _unique_codes(count)
    spec = cfg.cards[card_type]

    for code in batch_codes:
        url = qr.card_url(base_url, code)
        if OutputFormat.PDF in formats:
            pdf = render_card(spec, cfg.brand, code, url, cfg.validity_text, clips=clips)
            _write(directory / "pdf" / f"{code}.pdf", pdf)
        if OutputFormat.PNG in formats or OutputFormat.SVG in formats:
            symbol = qr.make(url)
            text = code if label else None
            (directory / "qr").mkdir(parents=True, exist_ok=True)
            if OutputFormat.PNG in formats:
                qr.save_png(symbol, directory / "qr" / f"{code}.png", label=text)
            if OutputFormat.SVG in formats:
                qr.save_svg(symbol, directory / "qr" / f"{code}.svg", label=text)

    card_format = "Digital" if OutputFormat.PDF in formats else "Fysisk"
    csv_path = directory / "batch.csv"
    import_path = directory / "import.csv"
    write_csv(csv_path, batch_codes, card_type, card_format, now, clips=clips, header=True)
    write_csv(import_path, batch_codes, card_type, card_format, now, clips=clips, header=False)
    return BatchResult(
        directory=directory, codes=batch_codes, csv_path=csv_path, import_path=import_path
    )


def write_csv(
    path: Path,
    batch_codes: Collection[str],
    card_type: CardType,
    card_format: str,
    generated: datetime,
    *,
    clips: int = 1,
    header: bool,
) -> None:
    """Write the batch's rows in the sheet's column order.

    Args:
        path: Destination file.
        batch_codes: Card codes, one row each.
        card_type: 60 or 90 minutes.
        card_format: ``Digital`` or ``Fysisk``.
        generated: Timestamp written to the ``Generert`` column.
        clips: Written to the ``Klipp`` column; ``Brukt`` starts at 0.
        header: Write the column names as the first row. Use ``False`` for the
            file that is appended to the sheet, since Sheets' *Append to current
            sheet* import has no "skip header" option.
    """
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(SHEET_COLUMNS)
        for code in batch_codes:
            row = dict.fromkeys(SHEET_COLUMNS, "")
            row |= {
                "Kode": code,
                "Type": card_type.value,
                "Format": card_format,
                "Status": STATUS_NOT_SOLD,
                "Generert": generated.strftime("%Y-%m-%d %H:%M"),
                "Klipp": str(clips),
                "Brukt": "0",
            }
            writer.writerow(row[column] for column in SHEET_COLUMNS)


def _unique_codes(count: int) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    while len(seen) < count:
        seen[codes.new_code()] = None
    return tuple(seen)


def _new_batch_dir(output_dir: Path, card_type: CardType, clips: int, now: datetime) -> Path:
    stem = f"{now:%Y-%m-%d_%H%M}_{card_type.value}min"
    if clips > 1:
        stem += f"_{clips}klipp"
    directory = output_dir / stem
    suffix = 2
    while directory.exists():
        directory = output_dir / f"{stem}_{suffix}"
        suffix += 1
    directory.mkdir(parents=True)
    return directory


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
