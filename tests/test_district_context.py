"""District context (NITI Aayog MPI 2023 and the Aspirational Districts list): read as published, checked, matched."""

import json
import re
import shutil
import subprocess

import pandas as pd
import pytest

from sdg_india import config
from sdg_india.sources import aspirational, mpi

EXTRACT = pd.read_csv(mpi.EXTRACT, dtype=str, keep_default_na=False)
PCT = re.compile(r"^\d{1,3}\.\d{2}%$")


def _f(v):
    return None if v in ("", "–", "-") else float(v.rstrip("%"))


def test_every_mpi_row_satisfies_mpi_equals_h_times_a():
    """Independent arithmetic check on each published row: MPI = headcount ratio x intensity (rounded)."""
    for r in EXTRACT.itertuples():
        for rnd in ("4", "5"):
            h, a, m = (_f(getattr(r, f"{k}{rnd}")) for k in ("hcr", "int", "mpi"))
            if h is None or (h == 0 and m in (None, 0)):
                continue
            assert abs(h / 100 * a / 100 - m) <= 0.0015, (r.district, rnd)


def test_mpi_values_are_in_range_and_as_published():
    for col in ("hcr4", "int4", "hcr5", "int5"):
        v = EXTRACT[col][~EXTRACT[col].isin(["", "–"])]
        assert v.str.match(PCT).all(), col
        assert v.map(_f).between(0, 100).all(), col
    assert EXTRACT["hcr5"].map(_f).notna().sum() >= 700      # every district has an NFHS-5 value


def test_aliases_point_to_real_districts_and_matching_is_one_to_one():
    ctx = pd.read_csv(config.PROCESSED / "district_context.csv", dtype=str, keep_default_na=False)
    geos = pd.read_csv(config.PROCESSED / "geographies.csv")
    ids = set(geos.loc[geos["geo_level"] == "district", "geo_id"])
    al = pd.read_csv(mpi.ALIASES)
    assert set(al["geo_id"]) <= ids
    assert set(aspirational.ALIASES.values()) <= ids
    assert ctx["geo_id"].is_unique and set(ctx["geo_id"]) == ids
    assert (ctx["mpi_hcr_nfhs5"] != "").sum() == len(ids)        # all 704 NFHS districts have an MPI value
    asp = ctx[ctx["aspirational"] == "True"]
    assert 100 <= len(asp) <= 112


def test_mpi_values_in_site_match_processed_table():
    d = json.loads((config.ROOT / "docs" / "data" / "districts.json").read_text())
    ctx = pd.read_csv(config.PROCESSED / "district_context.csv", dtype=str, keep_default_na=False).set_index("geo_id")
    for i, (gid, *_rest) in enumerate(d["districts"]):
        assert d["context"]["mpi5_raw"][i] == (ctx.at[gid, "mpi_hcr_nfhs5"] or None)
        assert d["context"]["asp"][i] == (ctx.at[gid, "aspirational"] == "True")


@pytest.mark.skipif(not mpi.PDF.exists() or not shutil.which("pdftotext"), reason="MPI report or Poppler missing")
def test_mpi_rows_confirmed_by_a_second_pdf_reader():
    """Poppler's text layout must show the same values on one line, in column order. The Bihar page has a hidden
    copy of Assam's table that Poppler interleaves; those rows were checked against the rendered page instead."""
    confirmed, total = 0, 0
    for page, sub in EXTRACT.groupby(EXTRACT["page"].astype(int)):
        txt = subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(mpi.PDF), "-"],
                             capture_output=True, text=True, check=True).stdout
        lines = [re.sub(r"\s+", " ", re.sub(r"(\d) %", r"\1%", ln)).strip() for ln in txt.split("\n")]
        for r in sub.itertuples():
            seq = " ".join(v for v in (r.hcr4, r.int4, r.mpi4, r.hcr5, r.int5, r.mpi5) if v)
            total += page != 108
            confirmed += page != 108 and any(seq in ln for ln in lines)
    assert confirmed == total


def test_aspirational_list_is_complete():
    df = pd.read_csv(aspirational.EXTRACT)
    assert df["s_no"].tolist() == list(range(1, 113))
