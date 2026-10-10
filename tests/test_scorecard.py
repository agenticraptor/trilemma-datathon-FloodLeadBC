"""Official-forecast scorecard rules on a synthetic event shaped like Nov 2021 (values chosen for the checks)."""

from datetime import UTC, datetime, timedelta

from floodlead import scorecard as sc

STAGES = {"action": 144.8, "minor": 146.5, "moderate": 148.0, "major": 150.0}
T0 = datetime(2021, 11, 14, 12, tzinfo=UTC)


def series() -> list[tuple[datetime, float]]:
    # rises 1 ft/h from 140 ft, crests at 150.76 ft at T0+10.76 h ... simplified: linear up, then down
    out = []
    for i in range(0, 4 * 30):
        t = T0 + timedelta(minutes=15 * i)
        h = i / 4
        out.append((t, round(140 + h if h <= 10.76 else 150.76 - (h - 10.76), 2)))
    return out


def test_observe_and_score() -> None:
    obs = sc.observe(series(), STAGES)
    assert obs is not None and obs.crest_ft == 150.75 and obs.minor_cross == T0 + timedelta(hours=6.5)
    prods = [
        {"issued_at": T0 + timedelta(hours=4), "action": "NEW", "severity": "2", "forecast_crest_ft": 148.9,
         "flood_crest": T0 + timedelta(hours=14), "flood_begin": T0 + timedelta(hours=7), "flood_end": None},
        {"issued_at": T0 + timedelta(hours=12), "action": "EXT", "severity": "3", "forecast_crest_ft": 150.5,
         "flood_crest": T0 + timedelta(hours=11), "flood_begin": None, "flood_end": None},
    ]
    onset = T0 + timedelta(hours=8)
    ev = sc.score_event(prods, obs, STAGES, onset)
    p0, p1 = ev["products"]
    assert p0["lead_h"] == 6.75 and p0["lead_bin"] == "6-12 h"
    assert p0["crest_error_ft"] == -1.85 and p0["category_forecast"] == "moderate" and p0["category_right"] is False
    assert p0["flood_begin_error_h"] == 0.5 and p0["crest_time_error_h"] == 3.25
    assert p1["lead_bin"] == "after the crest" and p1["category_right"] is True
    assert ev["first_warning_lead_before_minor_h"] == 2.5
    assert ev["major_product_after_overflow_onset_h"] == 4.0  # the "major" upgrade came after the overflow began
    s = sc.summarise([ev])
    b = {x["lead"]: x for x in s["lead_bins"]}
    assert b["6-12 h"]["crest_bias_ft"] == -1.85 and b["6-12 h"]["n_products"] == 1 and b["6-12 h"]["n_events"] == 1
    assert s["first_warning_lead_before_minor_h"]["median"] == 2.5


def test_category() -> None:
    assert sc.category(146.4, STAGES) == "action" and sc.category(150.0, STAGES) == "major"
    assert sc.category(140.0, STAGES) == "below action" and sc.category(None, STAGES) == "unknown"


def test_body_serialises_datetimes() -> None:
    import json

    assert json.dumps({"t": T0}, default=sc._iso) == '{"t": "2021-11-14T12:00:00Z"}'
