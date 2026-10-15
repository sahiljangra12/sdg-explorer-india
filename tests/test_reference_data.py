import json

import pandas as pd
import pytest

from sdg_india import config, geography, http
from sdg_india.io import explode_by_indicator, read_observations
from sdg_india.sources import niti


def test_geography_registry_has_36_current_states_and_uts():
    reg = geography.registry()
    assert reg["geo_id"].is_unique
    assert (reg["geo_level"] == "state").sum() == 28
    assert (reg["geo_level"] == "union_territory").sum() == 8


@pytest.mark.parametrize("name,expected", [
    ("Jammu & Kashmir", "IN.JK"), ("NCT of Delhi", "IN.DL"), ("Orissa", "IN.OD"), ("Andaman & Nicobar", "IN.AN"),
    ("Dadra and Nagar Haveli and Daman and Diu", "IN.DH"), ("Pondicherry", "IN.PY"), ("All India", "IN"),
    ("Uttaranchal", "IN.UK"), ("Atlantis", None),
])
def test_geography_aliases(name, expected):
    assert geography.resolve(name) == expected


def test_boundaries_match_registry():
    fc = json.loads((config.GEO / "india_states.geojson").read_text())
    ids = {f["properties"]["geo_id"] for f in fc["features"]}
    assert ids == set(geography.CURRENT_STATES_AND_UTS)
    assert "CC BY 4.0" in fc["attribution"]


def test_index_scores_are_separate_and_complete():
    df, status = niti.load_scores()
    latest = df[(df["edition"] == "2023-24") & (df["goal"] == 0) & (df["geo_level"] != "national")]
    assert len(latest) == 36 and latest["geo_id"].is_unique
    assert set(latest["geo_id"]) == set(geography.CURRENT_STATES_AND_UTS)
    assert df["score"].between(0, 100).all()
    assert config.SOURCE_BY_ID[niti.SOURCE_ID]["kind"] == "composite_index"
    assert df["verification"].str.startswith("verified").all()
    assert "published_change_vs_2020_21" not in df.columns        # not legible enough in the scanned report
    nat = df[(df["geo_id"] == "IN") & (df["goal"] == 0)].set_index("edition")["score"].to_dict()
    assert nat == {"2018": 57, "2019-20": 60, "2020-21": 66, "2023-24": 71}
    # values the report states in its text (p.66): Goal 13 rose from 54 to 67, Goal 1 from 60 to 72
    goal = df[(df["geo_id"] == "IN") & (df["goal"] > 0)].set_index(["edition", "goal"])["score"]
    stated = [("2020-21", 13), ("2023-24", 13), ("2020-21", 1), ("2023-24", 1)]
    assert [goal[k] for k in stated] == [54, 67, 60, 72]
    assert latest["score"].min() == 57 and latest["score"].max() == 79


def test_download_caches_and_records_provenance(tmp_path, monkeypatch):
    calls = []

    class FakeResp:
        status_code, content, url = 200, b'{"ok": true}', "https://example.org/x?y=1"

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            calls.append(url)
            return FakeResp()

    dest = tmp_path / "x.json"
    http.download("https://example.org/x", dest, params={"y": 1}, sess=FakeSession())
    http.download("https://example.org/x", dest, sess=FakeSession())          # cached: no second request
    assert len(calls) == 1
    meta = http.read_meta(dest)
    assert meta["url"] == FakeResp.url and len(meta["sha256"]) == 64


def test_download_never_writes_partial_files(tmp_path):
    class Bad:
        status_code, content, url = 503, b"", "https://example.org/x"

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            return Bad()

    with pytest.raises(http.DownloadError):
        http.download("https://example.org/x", tmp_path / "x.json", sess=FakeSession())
    assert not (tmp_path / "x.json").exists()


def test_retry_policy():
    adapter = http.session().get_adapter("https://unstats.un.org")
    assert adapter.max_retries.total == 5 and 503 in adapter.max_retries.status_forcelist


def test_processed_tables_exist_and_validate():
    manifest = json.loads((config.PROCESSED / "manifest.json").read_text())
    assert manifest["validation"]["errors"] == []
    obs = read_observations(config.PROCESSED / "observations.csv")
    totals = manifest["totals"]
    if obs.empty:
        assert totals["observations"] == 0
        return
    assert len(obs) == totals["records"] and obs["obs_id"].is_unique
    assert (obs["value_status"] != "not_available").sum() == totals["observations"]
    # published "NaN" markers survive the CSV round trip as text, not as empty cells
    na = obs[obs["value_status"] == "not_available"]
    assert len(na) == totals["not_available_markers"] and (na["value_raw"] != "").all()


def test_csv_round_trip_keeps_published_text(tmp_path):
    df = pd.DataFrame({"obs_id": ["a", "b"], "value": [1.5, None], "value_raw": ["1.5", "NaN"],
                       "value_status": ["numeric", "not_available"], "goal": [1, 1], "year": [2020, 2021],
                       "headline": [True, False], "indicator_codes_all": ["1.5.1;13.1.1", "1.1.1"]})
    df.to_csv(tmp_path / "o.csv", index=False)
    back = read_observations(tmp_path / "o.csv")
    assert back["value_raw"].tolist() == ["1.5", "NaN"] and back["value"].isna().tolist() == [False, True]
    ex = explode_by_indicator(back)
    assert sorted(ex[ex["obs_id"] == "a"]["goal"].tolist()) == [1, 13]


def test_processed_values_trace_back_to_raw_files():
    """Every sampled processed value must match a record in the raw file it cites, byte for byte."""
    obs = read_observations(config.PROCESSED / "observations.csv")
    obs = obs[obs["source_id"] == "UN_SDG_API"] if not obs.empty else obs
    if obs.empty:
        pytest.skip("no UN observations in this build")
    sample = obs.sample(n=min(300, len(obs)), random_state=7)
    cache = {}
    for r in sample.itertuples():
        raw_file = r.raw_file.split(" ; ")[0]
        if raw_file not in cache:
            cache[raw_file] = json.loads((config.RAW / raw_file).read_text(encoding="utf-8"))["data"]
        matches = [x for x in cache[raw_file]
                   if x["series"] == r.series_code and int(x["timePeriodStart"]) == r.year
                   and str(x["value"]) == r.value_raw
                   and json.dumps({k: v for k, v in sorted(x["dimensions"].items()) if k != "Reporting Type"},
                                  ensure_ascii=False, sort_keys=True) == r.dimensions]
        assert matches, f"{r.obs_id} not found in {raw_file}"
        assert http.sha256(config.RAW / raw_file) == r.raw_sha256.split(" ; ")[0]
