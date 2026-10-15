"""NFHS-5 District Fact Sheet parser, on SYNTHETIC sheets in the fact sheets' text layout."""

import pytest
from conftest import NFHS_SHEETS, use_synthetic_nfhs

from sdg_india.sources import nfhs


@pytest.mark.parametrize("raw,expected", [
    ("27.5", (27.5, "numeric", "")),
    ("(27.5)", (27.5, "numeric", "( ) = based on 25-49 unweighted cases")),
    ("1,024", (1024.0, "numeric", "")),
    ("na", (None, "not_available", "")),
    ("*", (None, "not_available", "* = percentage not shown, based on fewer than 25 unweighted cases")),
    ("abc", (None, "text", "")),
])
def test_cells(raw, expected):
    assert nfhs.cell(raw) == expected


def test_sheet_header_rounds_and_wrapped_rows():
    sh = nfhs.parse_sheet(NFHS_SHEETS[("uttar_pradesh", "Lucknow")])
    assert (sh["district"], sh["state"], sh["rounds"]) == ("Lucknow", "Uttar Pradesh", ("2019-21", "2015-16"))
    rows = {n: vals for n, _name, vals in sh["order"]}
    assert rows[9] == ["75.2", "49.0"]                            # name wrapped onto a second line
    assert rows[73] == ["(27.5)", "35.1"]


def test_new_district_has_one_round():
    sh = nfhs.parse_sheet(NFHS_SHEETS[("bihar", "Newpur")])
    assert sh["rounds"] == ("2019-21",) and {n: v for n, _, v in sh["order"]}[7] == ["95.5"]


def test_numbers_are_assigned_by_name_when_the_source_skips_one():
    canon = {nfhs.norm_name("Children under 5 years who are stunted (height-for-age)18 (%)"): [73]}
    rows, notes = nfhs.assign_numbers([(72, "Children under 5 years who are stunted (height-for-age) (%)",
                                        ["45.6"])], canon)
    assert rows == {73: ("Children under 5 years who are stunted (height-for-age) (%)", ["45.6"])}
    assert notes == ["printed number 72 is indicator 73 by its name"]


def test_load_all_end_to_end(tmp_path, monkeypatch):
    use_synthetic_nfhs(tmp_path, monkeypatch)
    res = nfhs.load_all()[nfhs.SOURCE_ID]
    df, st = res["data"], res["status"]
    assert st["districts"] == 3 and st["states_and_uts"] == 2
    assert df["obs_id"].is_unique and set(df["geo_level"]) == {"district"}
    by = {(r.geo_id, r.series_code, r.time_period): r for r in df.itertuples()}
    lk = by[("IN.UP.lucknow", "NFHS_D073", "NFHS-5 2019-21")]
    assert lk.value == 27.5 and "25-49" in lk.footnotes and lk.indicator_code == "2.2.1"
    assert by[("IN.UP.lucknow", "NFHS_D016", "NFHS-5 2019-21")].value_status == "not_available"
    # skipped number in the source: the Newpur value lands on indicator 73, not 72
    assert by[("IN.BR.newpur", "NFHS_D073", "NFHS-5 2019-21")].value == 45.6
    assert st["sheets_with_source_numbering_errors_corrected_by_name"] == 1
    # new district: no NFHS-4 rows at all (absent, not empty)
    assert not any(k[0] == "IN.BR.newpur" and k[2].startswith("NFHS-4") for k in by)
    # value split out of column order: left out and reported, never guessed
    assert ("IN.UP.agra", "NFHS_D010", "NFHS-5 2019-21") not in by
    assert any(p["file"] == "uttar_pradesh/agra.pdf" and "10" in p["problem"] for p in st["problems"])
    assert nfhs.EXTRACT.exists()


def test_extract_is_used_without_poppler(tmp_path, monkeypatch):
    use_synthetic_nfhs(tmp_path, monkeypatch)
    rows = len(nfhs.load_all()[nfhs.SOURCE_ID]["data"])
    monkeypatch.setattr(nfhs.shutil, "which", lambda name: None)
    res = nfhs.load_all()[nfhs.SOURCE_ID]
    assert res["status"]["status"] == "loaded from verified extract" and len(res["data"]) == rows
