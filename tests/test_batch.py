import csv
from datetime import datetime
from pathlib import Path

import pytest

from gavekort import batch, codes
from gavekort.batch import SHEET_COLUMNS, OutputFormat, generate
from gavekort.config import CardSpec, CardType, Config, ConfigError, load
from tests.conftest import write_config

NOW = datetime(2026, 10, 30, 13, 12)


def _read(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def _rows(path: Path) -> list[dict[str, str]]:
    """Rows of the header-less import file, keyed by column name."""
    return [dict(zip(SHEET_COLUMNS, row, strict=True)) for row in _read(path)]


def test_digital_batch_writes_pdfs_and_csv(cfg: Config) -> None:
    result = generate(CardType.MIN_60, 3, [OutputFormat.PDF], cfg, now=NOW)

    assert result.directory.name == "2026-10-30_1312_60min"
    assert sorted(p.stem for p in (result.directory / "pdf").iterdir()) == sorted(result.codes)
    assert not (result.directory / "qr").exists()
    rows = _rows(result.import_path)
    assert [r["Kode"] for r in rows] == list(result.codes)
    assert all(codes.is_valid(r["Kode"]) for r in rows)
    assert {(r["Type"], r["Format"], r["Status"], r["Generert"]) for r in rows} == {
        ("60", "Digital", "Ikke solgt", "2026-10-30 13:12")
    }
    assert all(r["Aktivert"] == r["Sist brukt"] == "" for r in rows)
    assert {(r["Klipp"], r["Brukt"]) for r in rows} == {("1", "0")}


def test_clip_card_batch(cfg: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    real_render = batch.render_card

    def spy(spec: CardSpec, *args: object, clips: int = 1) -> bytes:
        seen.append(clips)
        return real_render(spec, *args, clips=clips)  # type: ignore[arg-type]

    monkeypatch.setattr(batch, "render_card", spy)
    result = generate(CardType.MIN_90, 2, [OutputFormat.PDF], cfg, clips=5, now=NOW)

    assert result.directory.name == "2026-10-30_1312_90min_5klipp"
    assert {(r["Type"], r["Klipp"], r["Brukt"]) for r in _rows(result.import_path)} == {
        ("90", "5", "0")
    }
    assert seen == [5, 5]


def test_overview_csv_has_header_and_import_csv_does_not(cfg: Config) -> None:
    result = generate(CardType.MIN_60, 2, [OutputFormat.PDF], cfg, now=NOW)
    overview, to_import = _read(result.csv_path), _read(result.import_path)
    assert overview[0] == list(SHEET_COLUMNS)
    assert overview[1:] == to_import
    assert len(to_import) == 2
    assert all(row[0] in result.codes for row in to_import)


def test_physical_batch_writes_qr_images(cfg: Config) -> None:
    result = generate(CardType.MIN_90, 2, [OutputFormat.PNG, OutputFormat.SVG], cfg, now=NOW)

    names = sorted(p.name for p in (result.directory / "qr").iterdir())
    assert names == sorted(f"{c}.{ext}" for c in result.codes for ext in ("png", "svg"))
    assert not (result.directory / "pdf").exists()
    assert {r["Format"] for r in _rows(result.import_path)} == {"Fysisk"}


def test_batches_never_overwrite_each_other(cfg: Config) -> None:
    first = generate(CardType.MIN_60, 1, [OutputFormat.PDF], cfg, now=NOW)
    second = generate(CardType.MIN_60, 1, [OutputFormat.PDF], cfg, now=NOW)
    assert first.directory != second.directory
    assert first.csv_path.exists() and second.csv_path.exists()


def test_refuses_without_web_app_url(tmp_path: Path) -> None:
    cfg = load(write_config(tmp_path, web_app_url=""))
    with pytest.raises(ConfigError, match="web_app_url"):
        generate(CardType.MIN_60, 1, [OutputFormat.PDF], cfg)


def test_rejects_invalid_arguments(cfg: Config) -> None:
    with pytest.raises(ValueError):
        generate(CardType.MIN_60, 0, [OutputFormat.PDF], cfg)
    with pytest.raises(ValueError):
        generate(CardType.MIN_60, 1, [], cfg)
    with pytest.raises(ValueError):
        generate(CardType.MIN_60, 1, [OutputFormat.PDF], cfg, clips=0)
