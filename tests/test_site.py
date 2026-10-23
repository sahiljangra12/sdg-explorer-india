"""The static website (docs/) shows exactly the processed data: same counts, same values, nothing added."""

import json

import pytest

from sdg_india import config, site
from sdg_india.io import explode_by_indicator, read_observations


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    stats = site.build_site(config.PROCESSED, out)
    return out / "data", stats


def test_every_national_value_is_on_the_site_once_per_goal(built):
    data, _ = built
    obs = read_observations(config.PROCESSED / "observations.csv")
    nat = obs[obs["geo_level"] != "district"]
    seen = {}
    for f in sorted(data.glob("goal_*.json")):
        g = json.loads(f.read_text())
        for s in g["series"]:
            for grp in s["groups"]:
                for p in grp["pts"]:
                    seen.setdefault((g["goal"], s["source"], s["code"], grp["label"], p[1]), []).append(p[3])
    per_goal = explode_by_indicator(nat).drop_duplicates(["goal", "obs_id"])
    assert sum(len(v) for v in seen.values()) == len(per_goal)  # one point per observation and linked goal
    for r in per_goal.sample(400, random_state=1).itertuples():  # values copied as published
        hits = [v for k, v in seen.items() if k[0] == int(r.goal) and k[2] == r.series_code and k[4] == r.time_period]
        assert any(r.value_raw in v for v in hits), (r.series_code, r.time_period)


def test_district_columns_match_processed_rows(built):
    data, stats = built
    d = json.loads((data / "districts.json").read_text())
    obs = read_observations(config.PROCESSED / "observations.csv")
    dist = obs[obs["geo_level"] == "district"]
    assert stats["districts"] == dist["geo_id"].nunique() == len(d["districts"])
    n = sum(sum(x is not None for x in s["r5"]) + sum(x is not None for x in s["r4"]) for s in d["series"])
    assert n == len(dist)                                        # absent rounds are absent, not filled
    ids = [x[0] for x in d["districts"]]
    for r in dist.sample(300, random_state=2).itertuples():
        s = next(s for s in d["series"] if s["code"] == r.series_code)
        key = "r5" if r.time_period.startswith("NFHS-5") else "r4"
        assert s[key][ids.index(r.geo_id)] == r.value_raw


def test_site_page_references_only_files_that_exist(built):
    data, _ = built
    page = (config.ROOT / "docs" / "index.html").read_text()
    for name in ("summary.json", "districts.json", "india_states.geojson"):
        assert name in page and (data / name).exists()
    assert len(list(data.glob("goal_*.json"))) == 17


def test_paper_on_the_site_is_the_current_paper():
    src, served = config.ROOT / "paper" / "sdg_explorer_india.pdf", config.ROOT / "docs" / "paper.pdf"
    if src.exists():
        assert served.exists() and served.read_bytes() == src.read_bytes(), "run `python -m sdg_india site`"
