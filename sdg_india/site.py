"""Static website (GitHub Pages): exports the processed tables to compact JSON for ``docs/index.html``.

The page is plain HTML + JavaScript and reads only the files written here, so it needs no server.
Nothing is computed that the processed tables do not already contain: values, statuses and labels are copied.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pandas as pd

from . import config
from .io import explode_by_indicator, read_observations
from .labels import NATURE, dims_label, unit_label

SITE = config.ROOT / "docs"
REPO = "https://github.com/sahiljangra12/sdg-explorer-india"


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, 6)


def _csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() and path.stat().st_size > 2 else pd.DataFrame()


def _dump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def _short(desc: str) -> str:
    return desc.split("] ", 1)[1] if desc.startswith("[") and "] " in desc else desc


def national(obs: pd.DataFrame, indicators: pd.DataFrame, cov: pd.DataFrame) -> dict[int, dict]:
    """One file per goal: every national series, its breakdowns and every published value (incl. 'not available')."""
    nat = explode_by_indicator(obs[obs["geo_level"] != "district"])
    meta = {}
    if not indicators.empty:
        for r in indicators.drop_duplicates("series_code").itertuples():
            meta[r.series_code] = {"indicator_description": str(r.indicator_description or ""),
                                   "target_description": str(r.target_description or ""),
                                   "tier": "" if pd.isna(r.tier) else str(r.tier),
                                   "metadata_url": "" if pd.isna(r.metadata_url) else str(r.metadata_url)}
    gaps = {}
    if not cov.empty:
        for r in cov.itertuples():
            gaps[(r.source_id, r.series_code)] = {"gap_years": "" if pd.isna(r.gap_years) else str(r.gap_years)}
    out = {}
    for goal, g in nat.groupby("goal"):
        series = []
        for (src, code), s in g.groupby(["source_id", "series_code"], sort=True):
            s = s.drop_duplicates("obs_id").sort_values(["year", "time_period"])
            groups = []
            for dims, d in s.groupby("dimensions", sort=False):
                groups.append({
                    "label": dims_label(dims), "headline": bool(d["headline"].any()),
                    "pts": [[int(r.year), r.time_period, _num(r.value), r.value_raw, r.value_status,
                             _num(r.lower_bound), _num(r.upper_bound)] for r in d.itertuples()],
                })
            groups.sort(key=lambda x: (not x["headline"], x["label"] != "Total", x["label"]))
            numeric = s[s["value_status"] == "numeric"]
            notes = [f for f in s["footnotes"].dropna().astype(str).unique() if f][:8]
            urls = list(dict.fromkeys(s["source_url"].astype(str)))[:4]
            series.append({
                "code": code, "source": src, "desc": _short(str(s["series_description"].iloc[0])),
                "indicators": sorted({c for c in s["indicator_code"].astype(str) if c}),
                "unit": unit_label(str(s["unit"].iloc[0] or "")), "unit_multiplier": str(s["unit_multiplier"].iloc[0]),
                "n": int(len(numeric)), "na": int((s["value_status"] == "not_available").sum()),
                "first": int(numeric["year"].min()) if len(numeric) else None,
                "last": int(numeric["year"].max()) if len(numeric) else None,
                "original_source": list(dict.fromkeys(s["original_source"].dropna().astype(str)))[:4],
                "nature": sorted({NATURE.get(x, x) for x in s["nature"].astype(str) if x}),
                "release": list(dict.fromkeys(s["release"].dropna().astype(str)))[:3],
                "footnotes": notes, "urls": urls, **meta.get(code, {}), **gaps.get((src, code), {}),
                "groups": groups,
            })
        series.sort(key=lambda x: (x["n"] == 0, x["indicators"][0] if x["indicators"] else "", x["code"]))
        out[int(goal)] = {"goal": int(goal), "name": config.GOALS[int(goal)], "series": series}
    return out


def districts(obs: pd.DataFrame, geos: pd.DataFrame) -> dict:
    """District values as columns aligned to one district list; absent rounds stay null (never filled)."""
    d = obs[obs["geo_level"] == "district"].drop_duplicates("obs_id")
    if d.empty:
        return {"districts": [], "states": {}, "series": []}
    dl = geos[geos["geo_level"] == "district"].sort_values(["parent_geo_id", "geography"])
    names = dict(zip(geos["geo_id"], geos["geography"], strict=True))
    idx = {g: i for i, g in enumerate(dl["geo_id"])}
    series = []
    for code, s in d.groupby("series_code"):
        first = s.iloc[0]
        rec = {"code": code, "label": _short(str(first["series_description"])), "goal": int(first["goal"]),
               "target": str(first["target"]), "indicator": str(first["indicator_code"]), "unit": str(first["unit"]),
               "relation": str(first["footnotes"]).split(" | ")[1] if " | " in str(first["footnotes"]) else "",
               "nfhs": str(first["footnotes"]).split(" | ")[0]}
        for rnd, key in (("NFHS-5", "5"), ("NFHS-4", "4")):
            v, r = [None] * len(idx), [None] * len(idx)
            for row in s[s["time_period"].str.startswith(rnd)].itertuples():
                i = idx[row.geo_id]
                v[i], r[i] = _num(row.value), row.value_raw
            rec["v" + key], rec["r" + key] = v, r
        series.append(rec)
    series.sort(key=lambda x: (x["goal"], x["code"]))
    states = sorted(set(dl["parent_geo_id"]), key=lambda x: names.get(x, x))
    rows = zip(dl["geo_id"], dl["geography"], dl["parent_geo_id"], strict=True)
    return {"districts": [[g, n, p] for g, n, p in rows],
            "states": {s: names.get(s, s) for s in states}, "series": series}


def summary(obs, indicators, scores, sources, not_parsed, manifest, nat_files) -> dict:
    nat = explode_by_indicator(obs[obs["geo_level"] != "district"])
    numeric = nat[nat["value_status"] == "numeric"]
    goals = []
    for g in range(1, 18):
        ng = numeric[numeric["goal"] == g]
        ind = indicators[indicators["goal"] == g] if not indicators.empty else indicators
        no_data = ind[~ind["has_india_data"].astype(bool)] if len(ind) else ind
        years = ng.groupby("year")["series_code"].nunique()
        goals.append({
            "goal": g, "name": config.GOALS[g],
            "series_un": int(ng[ng["source_id"] == "UN_SDG_API"]["series_code"].nunique()),
            "series_mospi": int(ng[ng["source_id"] == "MOSPI_NIF_2025"]["series_code"].nunique()),
            "un_series_listed": int(ind["series_code"].nunique()) if len(ind) else 0,
            "un_series_no_india_data": [[str(r.indicator_code), str(r.series_code), str(r.series_description),
                                         "" if pd.isna(r.tier) else str(r.tier)]
                                        for r in no_data.drop_duplicates("series_code").itertuples()],
            "series_by_year": {int(y): int(n) for y, n in years.items()},
            "has_file": g in nat_files,
        })
    npd = not_parsed.fillna("") if not not_parsed.empty else not_parsed
    mospi_np = npd[npd["source_id"] == "MOSPI_NIF_2025"] if len(npd) else npd
    nfhs_np = npd[npd["source_id"] == "NFHS5_DISTRICTS"] if len(npd) else npd
    sc = scores.fillna("") if not scores.empty else scores
    return {
        "built": manifest.get("built_at", ""), "totals": manifest.get("totals", {}),
        "source_status": {k: {kk: vv for kk, vv in v.items() if isinstance(vv, (str, int, float))}
                          for k, v in manifest.get("source_status", {}).items()},
        "validation": manifest.get("validation", {}),
        "goals": goals,
        "sources": sources.fillna("").to_dict("records") if not sources.empty else [],
        "scores": sc.to_dict("records") if len(sc) else [],
        "mospi_not_parsed": [[str(r.code), str(r.goal).replace(".0", ""), str(r.name), str(r.reason),
                              str(r.page).replace(".0", "")] for r in mospi_np.itertuples()],
        "nfhs_notes": [[str(r.code), str(r.reason), str(r.kind)] for r in nfhs_np.itertuples()],
        "repo": REPO,
    }


def build_site(proc: Path | None = None, out: Path | None = None) -> dict:
    proc, out = proc or config.PROCESSED, out or SITE
    obs = read_observations(proc / "observations.csv")
    indicators, cov = _csv(proc / "indicators.csv"), _csv(proc / "coverage.csv")
    scores, sources = _csv(proc / "index_scores.csv"), _csv(proc / "sources.csv")
    not_parsed, geos = _csv(proc / "not_parsed.csv"), _csv(proc / "geographies.csv")
    manifest = json.loads((proc / "manifest.json").read_text()) if (proc / "manifest.json").exists() else {}
    data = out / "data"
    if data.exists():
        shutil.rmtree(data)
    nat = national(obs, indicators, cov)
    for g, payload in nat.items():
        _dump(payload, data / f"goal_{g:02d}.json")
    dist = districts(obs, geos)
    _dump(dist, data / "districts.json")
    meta = summary(obs, indicators, scores, sources, not_parsed, manifest, set(nat))
    _dump(meta, data / "summary.json")
    geo_src = config.GEO / "india_states.geojson"
    if geo_src.exists():
        shutil.copy(geo_src, data / "india_states.geojson")
    (out / ".nojekyll").write_text("")
    return {"goal_files": len(nat), "national_series": sum(len(p["series"]) for p in nat.values()),
            "districts": len(dist["districts"]), "district_series": len(dist["series"])}
