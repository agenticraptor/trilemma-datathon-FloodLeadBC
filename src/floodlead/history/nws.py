"""Parse archived NWS text products (IEM AFOS archive) into products and VTEC records (Stage 3 part 2; D-03.12).

A product: `\\x01`, a sequence number, the WMO line (`WGUS46 KSEW DDHHMM`), the AWIPS id (`FLWSEW`), then the text.
Its issuance time is the first local time line (`129 AM PST Sun Nov 28 2021`), converted to UTC with its zone and
checked against the WMO DDHHMM (UTC).
Segments end with `$$`. In each segment, every P-VTEC line
  /k.aaa.cccc.pp.s.####.yymmddThhnnZ-yymmddThhnnZ/
may be followed by an H-VTEC line
  /nwsli.s.ic.yymmddThhnnZ.yymmddThhnnZ.yymmddThhnnZ.fr/
(flood severity N/0/1/2/3/U, immediate cause, forecast flood begin, crest and end, flood record).
`000000T0000Z` means "not applicable / unknown" and becomes None.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

_T = r"(\d{6}T\d{4}Z)"
PVTEC = re.compile(r"/([OTEX])\.([A-Z]{3})\.([A-Z]{4})\.([A-Z]{2})\.([WAYSFON])\.(\d{4})\." + _T + "-" + _T + "/")
HVTEC = re.compile(r"/([A-Z0-9]{5})\.([0-3NU])\.([A-Z]{2})\." + _T + r"\." + _T + r"\." + _T + r"\.([A-Z]{2})/")
WMO = re.compile(r"^([A-Z]{4}\d{2}) ([A-Z]{4}) (\d{2})(\d{2})(\d{2})", re.M)
LOCAL = re.compile(r"^(\d{1,2})(\d{2}) (AM|PM) (PST|PDT|MST|MDT) \w{3} (\w{3}) (\d{1,2}) (\d{4})\s*$", re.M)
ZONES = {"PST": -8, "PDT": -7, "MST": -7, "MDT": -6}
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
                                      "Dec"], start=1)}
SEVERITY = {"N": "none", "0": "areal or no forecast point", "1": "minor", "2": "moderate", "3": "major",
            "U": "unknown"}


def vtec_time(s: str) -> datetime | None:
    if s.startswith("000000"):
        return None
    return datetime.strptime(s, "%y%m%dT%H%MZ").replace(tzinfo=UTC)


@dataclass
class Vtec:
    product_class: str
    action: str
    office: str
    phenomena: str
    significance: str
    etn: int
    begin: datetime | None
    end: datetime | None
    nwsli: str | None = None
    severity: str | None = None
    cause: str | None = None
    flood_begin: datetime | None = None
    flood_crest: datetime | None = None
    flood_end: datetime | None = None
    record: str | None = None
    segment: int = 0


@dataclass
class Product:
    pil: str
    wfo: str
    wmo: str
    issued_at: datetime
    text: str
    vtec: list[Vtec] = field(default_factory=list)


def issued_at(text: str) -> datetime | None:
    """UTC issuance: the first local time line, cross-checked with the WMO day/hour/minute (UTC)."""
    m = LOCAL.search(text)
    w = WMO.search(text)
    if not m:
        return None
    hh, mm, ampm, zone, mon, day, year = m.groups()
    h = int(hh) % 12 + (12 if ampm == "PM" else 0)
    local = datetime(int(year), MONTHS[mon], int(day), h, int(mm))
    t = (local - timedelta(hours=ZONES[zone])).replace(tzinfo=UTC)
    if w:
        wd, wh, wmin = int(w.group(3)), int(w.group(4)), int(w.group(5))
        if (t.day, t.hour, t.minute) != (wd, wh, wmin):
            # The WMO time is authoritative to the minute; keep the local date for month/year.
            cand = [t.replace(day=1) + timedelta(days=wd - 1, hours=wh - t.hour, minutes=wmin - t.minute)]
            cand += [c + timedelta(days=d) for c in cand for d in (-31, -30, -29, -28, 28, 29, 30, 31)]
            t = min((c for c in cand if c.day == wd), key=lambda c: abs((c - t).total_seconds()))
    return t


def parse_product(raw: str) -> Product | None:
    w = WMO.search(raw)
    if not w:
        return None
    lines = raw[w.end():].lstrip("\n").splitlines()
    pil = lines[0].strip() if lines else ""
    t = issued_at(raw)
    if t is None:
        return None
    p = Product(pil=pil, wfo=w.group(2), wmo=f"{w.group(1)} {w.group(2)} {w.group(3)}{w.group(4)}{w.group(5)}",
                issued_at=t, text=raw.strip("\x01\x03\n"))
    for si, seg in enumerate(raw.split("$$")):
        last: Vtec | None = None
        for line in seg.splitlines():
            pm = PVTEC.search(line)
            if pm:
                k, act, off, ph, sig, etn, b, e = pm.groups()
                last = Vtec(k, act, off, ph, sig, int(etn), vtec_time(b), vtec_time(e), segment=si)
                p.vtec.append(last)
                continue
            hm = HVTEC.search(line)
            if hm and last is not None and last.nwsli is None:
                nwsli, sev, ic, fb, fc, fe, fr = hm.groups()
                last.nwsli, last.severity, last.cause, last.record = nwsli, sev, ic, fr
                last.flood_begin, last.flood_crest, last.flood_end = vtec_time(fb), vtec_time(fc), vtec_time(fe)
    return p


def split_products(archive_text: str) -> list[str]:
    return [p for p in archive_text.split("\x01") if p.strip()]


def load(pool) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Parse every archived IEM page (history_downloads source 'iem-nws') into nws_products and nws_vtec.
    Idempotent: a product already stored (same pil, WMO line and issuance) is skipped."""
    from floodlead import archive
    from floodlead.config import get_settings

    s = get_settings()
    n_prod = n_vtec = skipped = 0
    with pool.connection() as conn:
        pages = conn.execute(
            "SELECT h.key, r.raw_object_id, r.archive_path FROM history_downloads h JOIN raw_objects r USING"
            " (raw_object_id) WHERE h.source = 'iem-nws' AND h.status = 'ok' ORDER BY h.key").fetchall()
        for _, rid, path in pages:
            text = archive.read(s.archive_dir, path).decode("latin-1")
            with conn.transaction():
                for raw in split_products(text):
                    p = parse_product(raw)
                    if p is None:
                        skipped += 1
                        continue
                    row = conn.execute(
                        "INSERT INTO nws_products (pil, wfo, wmo, issued_at, text, raw_object_id) VALUES"
                        " (%s, %s, %s, %s, %s, %s) ON CONFLICT (pil, wmo, issued_at) DO NOTHING"
                        " RETURNING product_id", (p.pil, p.wfo, p.wmo, p.issued_at, p.text, rid)).fetchone()
                    if row is None:
                        continue
                    n_prod += 1
                    with conn.cursor() as cur:
                        cur.executemany(
                            "INSERT INTO nws_vtec (product_id, seq, segment, issued_at, product_class, action, office,"
                            " phenomena, significance, etn, vtec_begin, vtec_end, nwsli, severity, cause, flood_begin,"
                            " flood_crest, flood_end, record) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                            " %s, %s, %s, %s, %s, %s, %s)",
                            [(row[0], i, v.segment, p.issued_at, v.product_class, v.action, v.office, v.phenomena,
                              v.significance, v.etn, v.begin, v.end, v.nwsli, v.severity, v.cause, v.flood_begin,
                              v.flood_crest, v.flood_end, v.record) for i, v in enumerate(p.vtec)])
                    n_vtec += len(p.vtec)
    return {"pages": len(pages), "products": n_prod, "vtec": n_vtec, "unparsed": skipped}
