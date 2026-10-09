"""NWS VTEC parsing on real archived products (IEM, FLWSEW, Nov 2021)."""

from datetime import UTC, datetime
from pathlib import Path

from floodlead.history import nws

FIX = Path(__file__).parent / "fixtures" / "iem_FLWSEW_2021_excerpt.txt"


def products() -> list[nws.Product]:
    out = [nws.parse_product(r) for r in nws.split_products(FIX.read_text(encoding="latin-1"))]
    return [p for p in out if p is not None]


def test_issuance_times_match_the_wmo_header() -> None:
    ps = products()
    assert [p.wmo for p in ps] == ["WGUS46 KSEW 151007", "WGUS46 KSEW 141950", "WGUS46 KSEW 280929"]
    assert ps[2].issued_at == datetime(2021, 11, 28, 9, 29, tzinfo=UTC)  # "129 AM PST Sun Nov 28 2021"
    assert all(p.pil == "FLWSEW" and p.wfo == "KSEW" for p in ps)


def test_pvtec_and_hvtec_for_north_cedarville() -> None:
    ps = products()
    first = [v for v in ps[1].vtec if v.nwsli == "NRKW1"][0]
    assert (first.action, first.phenomena, first.significance, first.etn) == ("NEW", "FL", "W", 78)
    assert first.severity == "2" and first.cause == "ER" and first.record == "NO"
    assert first.flood_begin == datetime(2021, 11, 14, 22, 18, tzinfo=UTC)
    assert first.flood_crest == datetime(2021, 11, 15, 18, 0, tzinfo=UTC)
    assert first.forecast_crest_ft == 148.9  # the first warning's crest (observed: 150.76 ft)
    upg = [v for v in ps[0].vtec if v.nwsli == "NRKW1"][0]
    assert (upg.action, upg.severity, upg.record, upg.begin) == ("EXT", "3", "NR", None)  # 000000T0000Z -> None
    nov28 = [v for v in ps[2].vtec if v.nwsli == "NRKW1"][0]
    assert (nov28.etn, nov28.flood_end) == (88, datetime(2021, 11, 29, 18, 28, tzinfo=UTC))
    # "a crest of 148.5 feet" is the forecast; "a previous crest of 148.1 feet on 12/13/2010" is history, not used
    assert (nov28.forecast_crest_ft, nov28.observed_stage_ft) == (148.5, 144.0)


def test_every_pvtec_is_kept_even_without_hvtec() -> None:
    ps = products()
    assert sum(len(p.vtec) for p in ps) >= 4
    assert all(v.product_class == "O" for p in ps for v in p.vtec)


def test_load_from_the_archive_is_idempotent(conn, test_dsn: str, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    from floodlead import archive, db, http
    from floodlead.config import get_settings
    from floodlead.history import download

    monkeypatch.setenv("ARCHIVE_DIR", str(tmp_path))
    get_settings.cache_clear()
    f = http.Fetched(url="https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py?pil=FLWSEW", status=200,
                     content=FIX.read_bytes(), last_modified=None, fetched_at=datetime(2026, 10, 9, tzinfo=UTC),
                     elapsed_s=0.1)
    ref = archive.store(conn, tmp_path, "iem-nws", "FLWSEW_2021", f)
    download.record(conn, "iem-nws", download.Task("FLWSEW/2021", f.url), f.url, "ok", 200, len(f.content),
                    ref.raw_object_id, f.fetched_at, 0.1, None)
    pool = db.pool(test_dsn, max_size=1)
    try:
        first = nws.load(pool)
        again = nws.load(pool)
    finally:
        pool.close()
        get_settings.cache_clear()
    assert first["products"] == 3 and first["vtec"] >= 4 and first["unparsed"] == 0
    assert again["products"] == 0  # idempotent
    row = conn.execute("SELECT v.issued_at, v.action, v.severity, v.flood_begin FROM nws_vtec v WHERE nwsli = 'NRKW1'"
                       " ORDER BY issued_at LIMIT 1").fetchone()
    assert row == (datetime(2021, 11, 14, 19, 50, tzinfo=UTC), "NEW", "2", datetime(2021, 11, 14, 22, 18, tzinfo=UTC))
    conn.execute("TRUNCATE nws_vtec, nws_products")


def test_upper_case_dates_in_older_products() -> None:
    raw = "\x01\n123 \nWGUS46 KSEW 140350\nFLWSEW\n\nFLOOD WARNING\n750 PM PST MON DEC 13 2010\n\n$$\n"
    assert nws.issued_at(raw) == datetime(2010, 12, 14, 3, 50, tzinfo=UTC)


def test_correction_heading_keeps_the_product_id() -> None:
    raw = ("\x01\n601 \nWGUS46 KSEW 100623 CCA\nFLWSEW\n\nFlood Warning\n1023 PM PST Tue Dec 9 2025\n\n"
           "/O.COR.KSEW.FL.W.0047.000000T0000Z-251211T1400Z/\n/NRKW1.2.ER.251210T2028Z.251211T0600Z.251212T0200Z.NO/\n$$\n")
    p = nws.parse_product(raw)
    assert p is not None and p.pil == "FLWSEW" and p.wmo == "WGUS46 KSEW 100623 CCA"
    assert p.issued_at == datetime(2025, 12, 10, 6, 23, tzinfo=UTC) and p.vtec[0].action == "COR"


def test_full_month_names_in_outlooks() -> None:
    raw = "\x01\n000 \nFGUS76 KSEW 192217 CCA\nESFSEW\n\nHYDROLOGIC OUTLOOK\n310 PM PDT MON JULY 19 2004\n\n$$\n"
    p = nws.parse_product(raw)
    # a correction (CCA) sent at 22:17Z keeps the original's text time (3:10 PM PDT = 22:10Z): the WMO time wins
    assert p is not None and p.pil == "ESFSEW" and p.issued_at == datetime(2004, 7, 19, 22, 17, tzinfo=UTC)
