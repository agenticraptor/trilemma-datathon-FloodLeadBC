"""Unit conversions, the sentinel rule, archive immutability and USGS chunk planning."""

from __future__ import annotations

import gzip
import hashlib
import os
import stat
from datetime import UTC, datetime

import pytest

from floodlead import archive, units
from floodlead.sources.usgs import covered, month_chunks


def test_conversions() -> None:
    assert units.to_si(1.0, "ft") == pytest.approx(0.3048)
    assert units.to_si(1.0, "ft3/s") == pytest.approx(0.028316846592)
    assert units.to_si(52300.0, "ft3/s") == pytest.approx(1480.97, rel=1e-4)
    assert units.to_si(2.5, "m") == 2.5
    with pytest.raises(ValueError):
        units.to_si(1.0, "furlong")


@pytest.mark.parametrize(
    ("param", "raw", "expected"),
    [
        ("level", 99999.0, True),      # ECCC sentinel (real, 08NJ026)
        ("level", -99999.0, True),
        ("level", 9999.0, True),       # prompt rule for levels
        ("level", 753.432, False),     # highest real ECCC level seen (geodetic datum)
        ("flow", 52300.0, False),      # Everson 2021 peak in ft3/s is real
        ("flow", 12000.0, False),      # a large-river freshet flow in m3/s must not be flagged
        ("flow", -9999.0, True),       # NWS/USGS missing code
        ("flow", -999999.0, True),     # USGS legacy missing code
        ("flow", 99999.0, True),
        ("flow", None, False),
    ],
)
def test_sentinel_rule(param: str, raw: float | None, expected: bool) -> None:
    assert units.is_sentinel(param, raw) is expected


def test_si_value_nulls_sentinels() -> None:
    assert units.si_value("level", 99999.0, "m") == (None, True)
    assert units.si_value("level", 1.5, "m") == (1.5, False)


def test_archive_write_is_atomic_readonly_deterministic_and_never_overwrites(tmp_path) -> None:
    data = b"ID,Date\n08MH001,2026-10-07T00:00:00-08:00\n"
    sha = archive.sha256_hex(data)
    rel = archive.relative_path("eccc", "BC_08MH001_hourly_hydrometric.csv", sha,
                                datetime(2026, 10, 7, 21, 3, tzinfo=UTC))
    assert rel == f"raw/eccc/2026/10/07/21/BC_08MH001_hourly_hydrometric.csv.{sha[:8]}.gz"
    size = archive.write_file(tmp_path, rel, data)
    f = tmp_path / rel
    assert size == f.stat().st_size
    assert stat.S_IMODE(f.stat().st_mode) == 0o444
    assert hashlib.sha256(gzip.decompress(f.read_bytes())).hexdigest() == sha
    first_bytes = f.read_bytes()
    # Same payload again: identical gzip bytes (mtime 0), existing file kept, no temp files left.
    archive.write_file(tmp_path, rel, data)
    assert f.read_bytes() == first_bytes
    archive.write_file(tmp_path, rel, b"different payload with the same name")
    assert f.read_bytes() == first_bytes
    assert [p.name for p in f.parent.iterdir()] == [f.name]
    assert not os.access(f, os.W_OK) or os.geteuid() == 0


def test_safe_name() -> None:
    assert archive.safe_name("gauge/NRKW1?x=1") == "gauge_NRKW1_x_1"


def test_month_chunks_and_coverage() -> None:
    c = month_chunks(datetime(2004, 10, 15, 7, tzinfo=UTC), datetime(2006, 2, 1, tzinfo=UTC), 6)
    assert [(a.date().isoformat(), b.date().isoformat()) for a, b in c] == [
        ("2004-10-15", "2005-01-01"), ("2005-01-01", "2005-07-01"),
        ("2005-07-01", "2006-01-01"), ("2006-01-01", "2006-02-01"),
    ]
    monthly = month_chunks(datetime(2021, 1, 1, tzinfo=UTC), datetime(2021, 7, 1, tzinfo=UTC), 1)
    assert len(monthly) == 6
    h1 = (datetime(2021, 1, 1, tzinfo=UTC), datetime(2021, 7, 1, tzinfo=UTC))
    assert covered(monthly, *h1)
    assert not covered(monthly[:5], *h1)
    assert not covered([], *h1)
