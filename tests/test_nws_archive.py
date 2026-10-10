"""Archive completeness (supervisor addendum 3, section 3): whole calendar years are downloaded, and the archive holds
every North Cedarville warning event since the SR 544 record began, including ETN 0088 (Nov 28, 2021, 1:29 AM PST),
which a partial-year pull once missed. The fixture holds every archived FLWSEW/FLSSEW product naming NRKW1 from
2015-11-14 to 2026-10-09 (75 products), cut from the whole-year IEM downloads."""

from datetime import UTC, datetime
from pathlib import Path

from floodlead.history import nws, tasks

FIX = Path(__file__).parent / "fixtures" / "iem_nrkw1_2015_2026.txt"

# The supervisor's independent list (addendum 3, section 2): 18 events. Times are the first (NEW) product, UTC.
EXPECTED_ANCHORS = {78: datetime(2021, 11, 14, 19, 50, tzinfo=UTC),   # 11:50 AM PST Nov 14, 2021
                    88: datetime(2021, 11, 28, 9, 29, tzinfo=UTC),    # 1:29 AM PST Nov 28, 2021 (the one once missed)
                    47: datetime(2025, 12, 10, 6, 17, tzinfo=UTC)}    # 10:17 PM PST Dec 9, 2025


def events() -> dict[tuple[int, int], datetime]:
    out: dict[tuple[int, int], datetime] = {}
    for raw in nws.split_products(FIX.read_text(encoding="latin-1")):
        p = nws.parse_product(raw)
        assert p is not None
        for v in p.vtec:
            if v.nwsli == "NRKW1" and v.phenomena == "FL" and v.significance == "W" and v.action == "NEW":
                wy = p.issued_at.year + 1 if p.issued_at.month >= 10 else p.issued_at.year
                out.setdefault((v.etn, wy), p.issued_at)
    return out


def test_all_18_warning_events_since_nov_2015() -> None:
    ev = events()
    assert len(ev) == 18
    first = {etn: t for (etn, _), t in ev.items()}
    for etn, t in EXPECTED_ANCHORS.items():
        assert first[etn] == t
    assert min(ev.values()) == datetime(2015, 11, 17, 23, 40, tzinfo=UTC)
    assert max(ev.values()) == datetime(2026, 3, 20, 23, 16, tzinfo=UTC)


def test_downloads_cover_whole_calendar_years_without_gaps() -> None:
    ts = tasks.iem_nws()
    for pil in ("FLWSEW", "FLSSEW", "FFASEW", "ESFSEW"):
        ys = sorted(int(t.key.split("/")[1]) for t in ts if t.key.startswith(pil + "/"))
        assert ys == list(range(tasks.FIRST_YEAR, ys[-1] + 1)) and ys[-1] >= 2026
        for t in ts:
            if t.key.startswith(pil + "/"):
                y = int(t.key.split("/")[1])
                assert (t.params["sdate"], t.params["edate"]) == (f"{y}-01-01", f"{y + 1}-01-01")
