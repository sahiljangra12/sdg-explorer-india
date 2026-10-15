import json

import pandas as pd
import pytest
from conftest import write_pages

from sdg_india.sources import un_sdg
from sdg_india.validate import ValidationError, validate


def parsed(folder):
    return un_sdg.parse_observations(un_sdg.load_pages(folder), un_sdg.series_releases(folder))


def test_strict_value_parsing():
    assert un_sdg.parse_value("12.5") == 12.5
    assert un_sdg.parse_value("-3") == -3.0
    assert un_sdg.parse_value("1e3") == 1000.0
    for raw in ["<0.1", ">95", "N", "NaN", "", None, "12,5"]:
        assert un_sdg.parse_value(raw) is None


def test_complete_download_loads(synthetic_pages):
    pages = un_sdg.load_pages(synthetic_pages)
    assert [p[0]["pageNumber"] for p in pages] == [1, 2, 3]


def test_missing_page_is_an_error(tmp_path):
    folder = write_pages(tmp_path / "un", drop_page=2)
    with pytest.raises(un_sdg.IncompleteDownload, match="missing"):
        un_sdg.load_pages(folder)


def test_record_count_mismatch_is_an_error(tmp_path):
    folder = write_pages(tmp_path / "un", total_override=99)
    with pytest.raises(un_sdg.IncompleteDownload, match="got 9"):
        un_sdg.load_pages(folder)


def test_parse_keeps_every_record_and_breakdown(synthetic_pages, goal_list):
    df = parsed(synthetic_pages)
    assert len(df) == 9 and df["obs_id"].is_unique
    s1 = df[df["series_code"] == "SYN_S1"]
    assert set(s1["dimensions"].map(lambda d: json.loads(d)["Sex"])) == {"BOTHSEX", "MALE", "FEMALE"}
    assert (df["geo_id"] == "IN").all()
    assert (s1["release"] == "2026.Q1").all()
    assert s1["goal"].iloc[0] == 1 and s1["indicator_code"].iloc[0] == "1.1.1"


def test_no_interpolation_of_missing_years(synthetic_pages):
    df = parsed(synthetic_pages)
    years = sorted(df[(df["series_code"] == "SYN_S1") & df["headline"]]["year"])
    assert years == [2015, 2016, 2018]          # 2017 stays missing


def test_ranges_are_kept_as_text_not_numbers(synthetic_pages):
    df = parsed(synthetic_pages)
    r = df[(df["series_code"] == "SYN_S3") & (df["year"] == 2020)].iloc[0]
    assert pd.isna(r["value"]) and r["value_raw"] == ">99"


def test_headline_flags(synthetic_pages):
    df = parsed(synthetic_pages)
    s1 = df[df["series_code"] == "SYN_S1"]
    assert set(s1[s1["headline"]]["dimensions"]) == {json.dumps({"Sex": "BOTHSEX"})}
    # a series published only for one age group: its only breakdown is the headline
    assert df[df["series_code"] == "SYN_S2"]["headline"].all()


def test_validation_passes_on_parsed_data(synthetic_pages):
    report = validate(parsed(synthetic_pages))
    assert report["errors"] == [] and any("kept as text" in w for w in report["warnings"])


def test_validation_rejects_duplicates_and_unexplained_gaps(synthetic_pages):
    df = parsed(synthetic_pages)
    with pytest.raises(ValidationError, match="duplicate"):
        validate(pd.concat([df, df.iloc[[0]]]))
    bad = df.copy()
    bad.loc[0, ["value", "value_raw"]] = [None, ""]
    with pytest.raises(ValidationError, match="neither a numeric value"):
        validate(bad)


def test_validation_rejects_composite_scores_in_observations(synthetic_pages):
    df = parsed(synthetic_pages)
    df.loc[0, "source_id"] = "NITI_SDGII_2023_24"
    with pytest.raises(ValidationError, match="Composite index"):
        validate(df)


def test_import_identifies_pages_by_content(tmp_path, monkeypatch):
    src = write_pages(tmp_path / "downloaded")
    for f in src.glob("india_page_????.json"):             # rename like a curl download would
        f.rename(src / f"un_india_page_{int(f.stem[-4:]):02d}.json")
    for m in src.glob("*.meta.json"):
        m.unlink()
    empty = {"size": 4, "totalElements": 9, "totalPages": 3, "pageNumber": 7, "data": []}
    (src / "un_india_page_07.json").write_text(json.dumps(empty))
    raw = tmp_path / "raw"
    monkeypatch.setattr(un_sdg, "RAW_DIR", raw)
    imported = un_sdg.import_files(src)
    assert sorted(p.name for p in imported) == ["india_page_0001.json", "india_page_0002.json", "india_page_0003.json"]
    assert (raw / "india_page_0001.json.meta.json").exists()
    assert len(parsed(raw)) == 9


def test_metadata_lists_series_without_data(goal_list):
    meta = un_sdg.parse_metadata(goal_list)
    assert set(meta["series_code"]) == {"SYN_S1", "SYN_NODATA"}
    assert meta["metadata_url"].str.startswith("https://unstats.un.org/sdgs/metadata/").all()


def test_failed_refresh_keeps_existing_data(tmp_path, monkeypatch):
    raw = write_pages(tmp_path / "un_sdg")
    before = {f.name: f.read_bytes() for f in raw.glob("india_page_????.json")}
    monkeypatch.setattr(un_sdg, "RAW_DIR", raw)
    calls = {"n": 0}

    def flaky_download(url, dest, params=None, sess=None, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise un_sdg.DownloadError("simulated network failure on page 2")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({"size": 1, "totalElements": 3, "totalPages": 3, "pageNumber": 1, "data": [{}]}))
        return dest

    monkeypatch.setattr(un_sdg, "download", flaky_download)
    with pytest.raises(un_sdg.DownloadError):
        un_sdg.fetch(refresh=True)
    after = {f.name: f.read_bytes() for f in raw.glob("india_page_????.json")}
    assert after == before                              # the verified data were not touched
    assert len(parsed(raw)) == 9


def test_multi_indicator_repeats_are_merged_and_conflicts_rejected(tmp_path):
    from conftest import SYNTHETIC_RECORDS, _rec
    shared = _rec("SYN_M", "12.2.2", 2019, "0.5", {})
    shared["indicator"] = ["12.2.2", "8.4.2"]
    folder = write_pages(tmp_path / "a", records=[shared] + SYNTHETIC_RECORDS + [dict(shared)])  # different pages
    df = parsed(folder)
    assert len(df) == 10 and df.attrs["repeats_merged"] == 1
    assert " ; " in df[df["series_code"] == "SYN_M"]["raw_file"].iloc[0]       # both pages kept
    conflict = dict(shared, value="0.6")
    folder = write_pages(tmp_path / "b", records=SYNTHETIC_RECORDS + [shared, conflict])
    with pytest.raises(un_sdg.IncompleteDownload, match="different content"):
        parsed(folder)
