"""Command-line interface: ``uv run gavekort <command>``.

Commands:
    generate  Create a batch of cards (PDFs and/or QR images) and a CSV for the sheet.
    preview   Render one sample card to check the design; does not touch any CSV.
"""

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from gavekort import batch, qr
from gavekort.card import render_card
from gavekort.config import CardType, Config, ConfigError, load

_PREVIEW_URL = "https://script.google.com/macros/s/PREVIEW/exec"
_PREVIEW_CODE = "GK-ABCD-EFGH"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        cfg = load(Path(args.config))
        if args.command == "generate":
            return _generate(args, cfg)
        return _preview(args, cfg)
    except ConfigError as e:
        print(f"Konfigurasjonsfeil: {e}", file=sys.stderr)
        return 2


def _generate(args: argparse.Namespace, cfg: Config) -> int:
    result = batch.generate(
        CardType(args.type),
        args.count,
        args.format,
        cfg,
        clips=args.klipp,
        label=args.label,
    )
    kind = f"{args.klipp} × {args.type} min" if args.klipp > 1 else f"{args.type} min"
    print(f"Laget {len(result.codes)} gavekort ({kind}) i {result.directory}")
    print(f"Oversikt: {result.csv_path}")
    print(f"Importer {result.import_path} i arket: Fil → Importer → Legg til i gjeldende ark.")
    return 0


def _preview(args: argparse.Namespace, cfg: Config) -> int:
    card_type = CardType(args.type)
    url = qr.card_url(cfg.web_app_url or _PREVIEW_URL, _PREVIEW_CODE)
    pdf = render_card(cfg.cards[card_type], cfg.brand, _PREVIEW_CODE, url, cfg.validity_text)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.output_dir / f"preview_{card_type.value}.pdf"
    path.write_bytes(pdf)
    print(f"Forhåndsvisning: {path}")
    if not args.no_open and sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    return 0


def _formats(value: str) -> list[batch.OutputFormat]:
    try:
        return [batch.OutputFormat(part.strip().lower()) for part in value.split(",") if part]
    except ValueError as e:
        valid = ", ".join(f.value for f in batch.OutputFormat)
        raise argparse.ArgumentTypeError(f"format must be a comma list of: {valid}") from e


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gavekort", description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="config.toml", help="path to config.toml")
    types = [t.value for t in CardType]
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="create a batch of gift cards")
    gen.add_argument("--type", required=True, choices=types, help="treatment length in minutes")
    gen.add_argument("--count", required=True, type=_positive_int, help="number of cards")
    gen.add_argument(
        "--format",
        type=_formats,
        default=[batch.OutputFormat.PDF],
        help="comma-separated: pdf (digital card), png and/or svg (QR for physical cards)",
    )
    gen.add_argument(
        "--klipp",
        type=_positive_int,
        default=1,
        help="treatments per card (default 1); more than 1 makes a clip card",
    )
    gen.add_argument("--label", action="store_true", help="print the code under PNG/SVG QRs")

    prev = sub.add_parser("preview", help="render a sample card to check the design")
    prev.add_argument("--type", required=True, choices=types, help="treatment length in minutes")
    prev.add_argument("--no-open", action="store_true", help="do not open the PDF afterwards")
    return parser
