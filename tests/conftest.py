"""Shared fixtures.

The UN API fixtures below are SYNTHETIC: they copy the structure of the UNSD SDG API
responses with made-up values, so parsing and validation logic can be tested offline.
They are never written into data/ and never shown as real data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdg_india.http import write_meta  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _rec(series, ind, year, value, dims=None, units="PERCENT", **extra):
    goal = ind.split(".")[0]
    return {"goal": [goal], "target": [".".join(ind.split(".")[:2])], "indicator": [ind], "series": series,
            "seriesDescription": f"Synthetic series {series}", "seriesCount": "1", "geoAreaCode": "356",
            "geoAreaName": "India", "timePeriodStart": float(year), "value": value, "valueType": "Float",
            "time_detail": None, "timeCoverage": None, "upperBound": None, "lowerBound": None, "basePeriod": None,
            "source": "Synthetic survey", "geoInfoUrl": None, "footnotes": extra.get("footnotes", []),
            "attributes": {"Nature": "C", "Units": units}, "dimensions": dims or {}}


SYNTHETIC_RECORDS = [
    # S1: a series with a sex breakdown and a total; one year missing (2017)
    _rec("SYN_S1", "1.1.1", 2015, "21.5", {"Sex": "BOTHSEX"}),
    _rec("SYN_S1", "1.1.1", 2015, "20.0", {"Sex": "MALE"}),
    _rec("SYN_S1", "1.1.1", 2015, "23.0", {"Sex": "FEMALE"}),
    _rec("SYN_S1", "1.1.1", 2016, "19.5", {"Sex": "BOTHSEX"}),
    _rec("SYN_S1", "1.1.1", 2018, "15.0", {"Sex": "BOTHSEX"}, footnotes=["Synthetic footnote."]),
    # S2: published only for one age group (no total code)
    _rec("SYN_S2", "3.2.1", 2010, "45.1", {"Age": "<5Y"}, units="PER_1000_LIVE_BIRTHS"),
    _rec("SYN_S2", "3.2.1", 2012, "41.0", {"Age": "<5Y"}, units="PER_1000_LIVE_BIRTHS"),
    # S3: a value published as a range, which must not become a number
    _rec("SYN_S3", "7.1.1", 2020, ">99", {}),
    _rec("SYN_S3", "7.1.1", 2021, "99.6", {}),
]


def write_pages(folder: Path, records=SYNTHETIC_RECORDS, page_size=4, drop_page=None, total_override=None):
    folder.mkdir(parents=True, exist_ok=True)
    chunks = [records[i:i + page_size] for i in range(0, len(records), page_size)]
    total = total_override if total_override is not None else len(records)
    for n, chunk in enumerate(chunks, start=1):
        if n == drop_page:
            continue
        obj = {"_note": "SYNTHETIC TEST FIXTURE - not real data", "size": page_size, "totalElements": total,
               "totalPages": len(chunks), "pageNumber": n, "attributes": [], "dimensions": [], "data": chunk}
        page = folder / f"india_page_{n:04d}.json"
        page.write_text(json.dumps(obj), encoding="utf-8")
        write_meta(page, f"https://synthetic.invalid/Indicator/Data?page={n}", 200, note="synthetic fixture")
    return folder


@pytest.fixture
def synthetic_pages(tmp_path):
    return write_pages(tmp_path / "un_sdg")


@pytest.fixture
def goal_list(tmp_path):
    gl = [{"code": "1", "title": "Synthetic goal", "targets": [{"code": "1.1", "description": "Synthetic target",
          "indicators": [{"code": "1.1.1", "description": "Synthetic indicator", "tier": "1",
                          "series": [{"code": "SYN_S1", "description": "Synthetic series SYN_S1", "release": "2026.Q1"},
                                     {"code": "SYN_NODATA", "description": "No data series",
                                      "release": "2026.Q1"}]}]}]}]
    d = tmp_path / "un_sdg"
    d.mkdir(parents=True, exist_ok=True)
    (d / "goal_list.json").write_text(json.dumps(gl), encoding="utf-8")
    (d / "series_list.json").write_text(json.dumps([{"code": "SYN_S1", "release": "2026.Q1", "description": "x",
                                                      "goal": ["1"], "target": ["1.1"], "indicator": ["1.1.1"]}]))
    return d


# ---------------------------------------------------------------- NFHS district fact sheets (SYNTHETIC)
def nfhs_sheet(district, state, rows, rounds=("2019-21", "2015-16")):
    """Text in the layout pdftotext gives for an NFHS-5 District Fact Sheet. SYNTHETIC values."""
    head = "Indicators  " + "  ".join(f"({r})" for r in rounds)
    lines = ["", "District Fact Sheet", district, state, "", f"In {district}, information was gathered from "
             "households.", "", f"{district}, {state} - Key Indicators", head]
    for row in rows:
        if isinstance(row, str):                                  # a raw line (continuations, broken rows)
            lines.append(row)
        else:
            n, name, *vals = row
            lines.append(f"{n}. {name:<72}" + "".join(f"{v:>12}" for v in vals))
    return "\n".join(lines)


STUNTED = "Children under 5 years who are stunted (height-for-age)18 (%)"
ELECTRICITY = "Population living in households with electricity (%)"
MARRIED = "Women age 20-24 years married before age 18 years (%)"
SANITATION = "Population living in households that use an improved sanitation facility2 (%)"
CLEAN_FUEL = "Households using clean fuel for cooking3 (%)"
DIET = "Total children age 6-23 months receiving an adequate diet16, 17 (%)"

NFHS_SHEETS = {
    ("uttar_pradesh", "Lucknow"): nfhs_sheet("Lucknow", "Uttar Pradesh", [
        (7, ELECTRICITY, "98.1", "91.0"),
        (9, "Population living in households that use an improved"),
        "   sanitation facility2 (%)                                             75.2        49.0",
        (10, CLEAN_FUEL, "70.3", "61.0"),
        (16, MARRIED, "*", "21.4"),
        (72, DIET, "(18.7)", "9.0"),
        (73, STUNTED, "(27.5)", "35.1"),
    ]),
    ("uttar_pradesh", "Agra"): nfhs_sheet("Agra", "Uttar Pradesh", [
        (7, ELECTRICITY, "97.0", "90.2"),
        (9, SANITATION, "70.0", "45.3"),
        (10, "Households using clean fuel for cooking3 (%)"),
        "        55.0",                                           # values split out of column order
        (16, MARRIED, "na", "20.0"),
        (72, DIET, "11.0", "8.2"),
        (73, STUNTED, "33.4", "40.2"),
    ]),
    ("bihar", "Newpur"): nfhs_sheet("Newpur", "Bihar", [            # new district: NFHS-5 column only, and
        (7, ELECTRICITY, "95.5"),                                   # a skipped number in the source list
        (9, SANITATION, "40.1"),
        (10, CLEAN_FUEL, "20.2"),
        (16, MARRIED, "40.0"),
        (72, STUNTED, "45.6"),                                      # printed 72; by its name it is 73
    ], rounds=("2019-21",)),
}


def use_synthetic_nfhs(tmp_path, monkeypatch):
    from sdg_india.sources import nfhs
    raw = tmp_path / "raw" / "nfhs5_districts"
    texts = {}
    for (folder, district), text in NFHS_SHEETS.items():
        pdf = raw / folder / f"{district.lower()}.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4 synthetic\n%%EOF")
        texts[pdf] = text
    monkeypatch.setattr(nfhs, "RAW_DIR", raw)
    monkeypatch.setattr(nfhs, "EXTRACT", tmp_path / "reference" / "nfhs_extract.csv")
    monkeypatch.setattr(nfhs, "EXTRACT_STATUS", tmp_path / "reference" / "nfhs_extract_status.json")
    monkeypatch.setattr(nfhs, "page_text", lambda pdf: texts[pdf])
    monkeypatch.setattr(nfhs.shutil, "which", lambda name: "/usr/bin/" + name)
    return nfhs
