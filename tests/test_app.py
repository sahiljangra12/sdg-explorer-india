"""Run the dashboard headlessly: on the real processed data, and on a synthetic build that exercises every tab."""

import json
import shutil

import pytest
from conftest import use_synthetic_nfhs, write_pages
from streamlit.testing.v1 import AppTest

from sdg_india import build, config
from sdg_india.sources import mospi, nfhs, un_sdg

APP = str(config.ROOT / "app" / "app.py")


def run_app():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_app_runs_on_shipped_data():
    run_app()


def _build(tmp_path, monkeypatch, districts):
    """Build processed tables from SYNTHETIC UN pages (and, if asked, synthetic district sheets)."""
    raw = write_pages(tmp_path / "raw" / "un_sdg")
    proc = tmp_path / "processed"
    monkeypatch.setattr(un_sdg, "RAW_DIR", raw)
    monkeypatch.setattr(build, "OUT", proc)
    monkeypatch.setattr(config, "PROCESSED", proc)
    load_pages, releases, meta = un_sdg.load_pages, un_sdg.series_releases, un_sdg.parse_metadata
    monkeypatch.setattr(un_sdg, "load_pages", lambda raw_dir=raw: load_pages(raw_dir))
    monkeypatch.setattr(un_sdg, "series_releases", lambda raw_dir=raw: releases(raw_dir))
    monkeypatch.setattr(un_sdg, "parse_metadata", lambda raw_dir=raw: meta(raw_dir))
    monkeypatch.setattr(mospi, "load_all", lambda: {})          # keep the synthetic build to synthetic data
    monkeypatch.setattr(build, "write_coverage_report", lambda *a, **k: None)   # do not overwrite docs/
    if districts:
        use_synthetic_nfhs(tmp_path, monkeypatch)                # synthetic district sheets, not data/raw
    else:
        monkeypatch.setattr(nfhs, "load_all", lambda: {})
    shutil.copy(config.REFERENCE / "niti_index_scores.csv", tmp_path / "scores.csv")
    manifest = build.build()
    return manifest


@pytest.fixture
def synthetic_build(tmp_path, monkeypatch):
    return _build(tmp_path, monkeypatch, districts=False)


@pytest.fixture
def synthetic_build_with_districts(tmp_path, monkeypatch):
    return _build(tmp_path, monkeypatch, districts=True)


def test_app_runs_on_synthetic_build_and_every_tab_renders(synthetic_build):
    assert synthetic_build["totals"]["observations"] == 9
    at = run_app()
    assert at.metric[0].value == "9"
    assert len(at.tabs) == 7


def test_districts_tab_renders(synthetic_build_with_districts):
    assert synthetic_build_with_districts["validation"]["errors"] == []
    at = run_app()
    assert len(at.tabs) == 7
    # the Districts tab: pick a State, so the NFHS-4 -> NFHS-5 comparison chart renders too
    at.selectbox(key="d_state").select("Uttar Pradesh").run()
    assert not at.exception, [e.value for e in at.exception]
    inds = at.selectbox(key="d_ind").options
    at.selectbox(key="d_ind").select(next(o for o in inds if "stunted" in o)).run()
    assert not at.exception, [e.value for e in at.exception]


def test_manifest_counts_match(synthetic_build):
    t = synthetic_build["totals"]
    assert (t["series"], t["earliest_year"], t["latest_year"], t["text_observations"]) == (3, 2010, 2021, 1)
    assert t["not_available_markers"] == 0 and t["observations"] == 9
    assert t["observations_before_2015"] == 2
    assert json.loads(json.dumps(synthetic_build))["validation"]["errors"] == []
