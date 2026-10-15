"""MoSPI NIF report parser.

The snippets below copy the layout of the report's Data Snapshot pages (``pdftotext -layout``)
with the report's own values, so parsing rules can be tested without the 37 MB PDF.
"""

import json

import pytest

from sdg_india import config
from sdg_india.sources import mospi

PAD = " " * 60


def page(*lines):
    return "\n".join(lines)


SIMPLE = page(
    " Goal 1: End poverty in all its forms everywhere",
    " Target 1.3: Implement nationally appropriate social protection systems",
    " 2        1.3.2: Number of Self-Help Groups (SHGs) provided bank credit linkage,                   Year                    Value (in lakhs)",  # noqa: E501
    "          Source: National Bank for Agriculture and Rural Development",
    "          (NABARD), Ministry of Finance /Periodicity: Annual                                       2015-16                 18.32",  # noqa: E501
    "                                                                                                   2016-17                 18.98",  # noqa: E501
    " 3        1.3.3: Number of senior citizens provided institutional assistance through Senior        Year                    Value",  # noqa: E501
    "          Source: Department of Social Justice & Empowerment / Periodicity: Annual                 2019-20                 1,09,085",  # noqa: E501
    " 1        1.5.1: Number of deaths, missing persons and directly affected persons                  Year                      Value",  # noqa: E501
    "          Source: Disaster Management Division, Ministry of Home Affairs / Periodicity:           2023                      277 .0865",  # noqa: E501
    "          Annual                                                                                  2024                      66.6614*",  # noqa: E501
    "                                                                                                                            * During the Monsoon Period",  # noqa: E501
)

WRAPPED_HEADER_AND_DASHES = page(
    " Goal 5: Achieve gender equality",
    " 1      5.5.1: Proportion of seats held by women in (a) national",
    "        parliaments and (b) local governments (similar to 10.2.2)                    Year      Lok Sabha    ULB       PRI",  # noqa: E501
    "        Source: Election Commission of India                                         2014      11.42        -         46.14",  # noqa: E501
    "                                                                                     2019      14.36        43.16     44.37",  # noqa: E501
)

QUARTERS = page(
    " Goal 5: Achieve gender equality",
    " 3     5.a.4: Average agricultural wage earnings from casual",
    "       labour work other than public works (Rs.per day)         Quarter     Year      Male       Female",
    "       Source: PLFS, NSSO                                                   2017-18   222        159",
    "                                                       Jul - Sep",
    "                                                                            2018-19   236        164",
    "                                                                            2017-18   233        169",
    "                                                       Oct - Dec",
)

MULTILINE_HEADER = page(
    " Goal 15: Life on land",
    " 1    15.2.1: Progress towards sustainable forest                                   Net change   Above-",
    "      management                                                         Year       in area      ground",
    "      Source: FSI                                                         2019       0.56         3.1",
)


def parse(*pages):
    pages = list(pages)
    return mospi.parse_snapshot(pages, range(len(pages)))


@pytest.mark.parametrize("token,expected", [
    ("18.32", (18.32, "numeric", "")), ("1,09,085", (109085.0, "numeric", "")),
    ("277 .0865", (277.0865, "numeric", "")), ("66.6614*", (66.6614, "numeric", "*")),
    ("-", (None, "not_available", "")), ("NA", (None, "not_available", "")),
    ("(-)73.8", (None, "text", "")), ("Yes", (None, "text", "")),
])
def test_cell_values(token, expected):
    assert mospi.clean_number(token) == expected


def test_simple_tables_units_and_footnotes():
    rows, skipped = parse(SIMPLE)
    assert not skipped
    by = {(r["code"], r["period"]): r for r in rows}
    assert by[("1.3.2", "2015-16")]["value"] == 18.32 and by[("1.3.2", "2015-16")]["unit"] == "lakhs"
    assert by[("1.3.3", "2019-20")]["value"] == 109085                  # Indian digit grouping
    assert by[("1.5.1", "2023")]["value"] == 277.0865                   # stray space inside the number
    assert by[("1.5.1", "2024")]["footnote"] == "* During the Monsoon Period"
    assert by[("1.3.2", "2016-17")]["source"].startswith("National Bank for Agriculture")
    assert by[("1.3.2", "2016-17")]["periodicity"] == "Annual"
    assert by[("1.3.2", "2016-17")]["goal"] == 1 and by[("1.3.2", "2016-17")]["target"] == "1.3"


def test_header_on_a_later_line_and_dashes_keep_their_columns():
    rows, skipped = parse(WRAPPED_HEADER_AND_DASHES)
    assert not skipped
    got = {(r["period"], r["column"]): r["value_raw"] for r in rows}
    assert got[("2014", "Lok Sabha")] == "11.42" and got[("2014", "ULB")] == "-" and got[("2014", "PRI")] == "46.14"
    assert got[("2019", "ULB")] == "43.16"


def test_hidden_grouping_column_is_not_parsed():
    rows, skipped = parse(QUARTERS)
    assert rows == [] and "periods repeat" in skipped[0]["reason"]


def test_multi_line_header_is_not_guessed():
    rows, skipped = parse(MULTILINE_HEADER)
    assert rows == [] and "spans several lines" in skipped[0]["reason"]


def test_observations_have_provenance_and_headlines(tmp_path):
    rows, _ = parse(SIMPLE, WRAPPED_HEADER_AND_DASHES)
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.6 test\n%%EOF")
    df = mospi.to_observations(rows, pdf)
    assert df["obs_id"].is_unique
    assert df["source_url"].str.contains("#page=").all() and (df["raw_sha256"].str.len() == 64).all()
    simple = df[df["series_code"] == "NIF_1.3.2"]
    assert simple["headline"].all()                                     # single value column
    seats = df[df["series_code"] == "NIF_5.5.1"]
    assert not seats["headline"].any()                                  # no Total column: user picks
    assert set(seats["dimensions"].map(lambda d: json.loads(d)["Category"])) == {"Lok Sabha", "ULB", "PRI"}
    assert (df.loc[df["value_raw"] == "-", "value_status"] == "not_available").all()


@pytest.mark.skipif(not mospi.PDF.exists(), reason="MoSPI report not downloaded")
def test_every_published_mospi_value_was_confirmed_on_the_page():
    manifest = json.loads((config.PROCESSED / "manifest.json").read_text())
    st = manifest["source_status"]["MOSPI_NIF_2025"]
    assert st["dropped_unconfirmed"] == 0
    assert st["confirmed_by_word_positions"] + st["confirmed_visually"] == st["table_rows_checked"]
    assert st["indicators_parsed"] + st["indicators_not_parsed"] == st["indicators_in_snapshot"]


@pytest.mark.skipif(not mospi.EXTRACT.exists(), reason="no verified extract in this build")
def test_without_poppler_the_verified_extract_is_used(monkeypatch):
    monkeypatch.setattr(mospi.shutil, "which", lambda name: None)
    res = mospi.load_all()[mospi.SOURCE_ID]
    assert res["status"]["status"] == "loaded from verified extract"
    expected = "brew install poppler" if mospi.PDF.exists() else "not downloaded"
    assert expected in res["status"]["detail"]
    assert len(res["data"]) == res["status"]["rows"] and res["data"]["obs_id"].is_unique
    assert len(res["skipped"]) == res["status"]["indicators_not_parsed"]



@pytest.mark.skipif(not mospi.PDF.exists(), reason="MoSPI report not downloaded")
def test_the_two_parsers_agree_where_both_can_read_a_table():
    """The text-layout parser and the gridline parser are independent; on tables both can read they must agree."""
    import collections
    pages = mospi.page_texts(mospi.PDF)
    rng = mospi.snapshot_pages(pages)
    text_rows, _ = mospi.parse_snapshot(pages, rng)
    grid_rows, _ = mospi.parse_grid(mospi.PDF, rng, {r["code"] for r in text_rows})
    tv, gv = collections.defaultdict(list), collections.defaultdict(list)
    for r in text_rows:
        tv[(r["code"], r["period"])].append(r["value_raw"].replace(" ", ""))
    for r in grid_rows:
        gv[(r["code"], r["period"])].append(r["value_raw"].replace(" ", ""))
    common = set(tv) & set(gv)
    assert len(common) > 500
    assert [k for k in common if tv[k] != gv[k]] == []


def test_reviewed_gridline_tables_are_labelled_and_confirmed():
    manifest = json.loads((config.PROCESSED / "manifest.json").read_text())
    g = manifest["source_status"]["MOSPI_NIF_2025"].get("gridline_parser", {})
    if not g:
        pytest.skip("gridline parser did not run in this build")
    assert g["rejected"] == {} and g["rows_not_confirmed_dropped"] == 0
    assert g["tables_used"] == len(mospi.GRID_REVIEW)
