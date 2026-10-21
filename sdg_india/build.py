"""Assemble processed tables from the raw official files, validate them and report coverage."""

from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata

import pandas as pd

from . import config, geography
from .io import explode_by_indicator
from .sources import aspirational, mospi, mpi, nfhs, niti, un_sdg
from .validate import validate

OUT = config.PROCESSED


def _versions() -> dict:
    out = {"python": platform.python_version()}
    for pkg in ("pandas", "numpy", "pdfplumber", "streamlit", "plotly"):
        try:
            out[pkg] = importlib_metadata.version(pkg)
        except importlib_metadata.PackageNotFoundError:
            pass
    return out


def _districts_from(obs: pd.DataFrame) -> pd.DataFrame:
    """District registry rebuilt from an extract (geo_id is <state geo_id>.<district slug>)."""
    d = obs[obs["geo_level"] == "district"].drop_duplicates("geo_id")
    return pd.DataFrame({"geo_id": d["geo_id"], "geography": d["geography"], "geo_level": "district",
                         "parent_geo_id": d["geo_id"].str.rsplit(".", n=1).str[0]})


def coverage(obs: pd.DataFrame) -> pd.DataFrame:
    """One row per source, goal, indicator and series: what exists and over which years."""
    if obs.empty:
        return pd.DataFrame()
    ex = explode_by_indicator(obs)
    ex = ex[ex["value_status"] != "not_available"].assign(not_available=0)
    na = explode_by_indicator(obs[obs["value_status"] == "not_available"])
    g = pd.concat([ex, na.assign(not_available=1)]).groupby(["source_id", "goal", "indicator_code", "series_code"],
                                                           dropna=False)
    cov = g.agg(series_description=("series_description", "first"), unit=("unit", "first"),
                observations=("not_available", lambda s: int((s == 0).sum())),
                not_available_markers=("not_available", "sum"), numeric_observations=("value", "count"),
                geographies=("geo_id", "nunique"), first_year=("year", "min"), latest_year=("year", "max"),
                years_with_data=("year", "nunique"), breakdowns=("dimensions", "nunique")).reset_index()
    cov["span_years"] = cov["latest_year"] - cov["first_year"] + 1
    cov["gap_years"] = cov["span_years"] - cov["years_with_data"]
    return cov.sort_values(["goal", "indicator_code", "series_code"])


def summarise(obs: pd.DataFrame) -> dict:
    if obs.empty:
        return {"observations": 0}
    status = obs["value_status"]
    real = obs[status != "not_available"]
    ex = explode_by_indicator(real)
    return {
        "records": int(len(obs)),
        "observations": int(len(real)),
        "numeric_observations": int((status == "numeric").sum()),
        "text_observations": int((status == "text").sum()),
        "not_available_markers": int((status == "not_available").sum()),
        "goals_covered": sorted(int(x) for x in ex["goal"].dropna().unique()),
        "indicators": int(ex["indicator_code"].replace("", pd.NA).nunique()),
        "series": int(real["series_code"].nunique()),
        "geographies": int(real["geo_id"].nunique()),
        "earliest_year": int(real["year"].min()),
        "latest_year": int(real["year"].max()),
        "observations_before_2015": int((real["year"] < 2015).sum()),
    }


def district_context(districts: pd.DataFrame, status: dict, not_parsed: list) -> pd.DataFrame:
    """One row per NFHS district: NITI Aayog MPI (NFHS-4 and NFHS-5) and Aspirational District status.

    Values are copied as published. A district without a match keeps empty cells; nothing is filled in."""
    cols = ["geo_id", "mpi_hcr_nfhs5", "mpi_intensity_nfhs5", "mpi_nfhs5", "mpi_hcr_nfhs4", "mpi_intensity_nfhs4",
            "mpi_nfhs4", "mpi_published_name", "mpi_report_page", "aspirational", "aspirational_published_name"]
    if districts.empty:
        return pd.DataFrame(columns=cols)
    out = districts[["geo_id"]].copy()
    res = mpi.load(districts)
    status[mpi.SOURCE_ID] = res["status"]
    not_parsed += [{"source_id": mpi.SOURCE_ID, "code": f"{r.get('state', '')}: {r.get('district', '')}".strip(": "),
                    "page": r.get("page", ""), "reason": r["reason"]} for r in res["skipped"]]
    d = res["data"]
    if len(d):
        d = d[d["geo_id"].notna()].rename(columns={"hcr5": "mpi_hcr_nfhs5", "int5": "mpi_intensity_nfhs5",
                                                     "mpi5": "mpi_nfhs5", "hcr4": "mpi_hcr_nfhs4",
                                                     "int4": "mpi_intensity_nfhs4", "mpi4": "mpi_nfhs4",
                                                     "district": "mpi_published_name", "page": "mpi_report_page"})
        out = out.merge(d[cols[:9]], on="geo_id", how="left")
    res = aspirational.load(districts)
    status[aspirational.SOURCE_ID] = res["status"]
    not_parsed += [{"source_id": aspirational.SOURCE_ID, "code": f"{r['state']}: {r['district']}",
                    "reason": r["reason"]} for r in res["skipped"]]
    a = res["data"]
    if len(a):
        a = a[a["geo_id"].notna()][["geo_id", "district"]].rename(columns={"district": "aspirational_published_name"})
        out = out.merge(a, on="geo_id", how="left")
        out["aspirational"] = out["aspirational_published_name"].notna()
    for c in cols:
        if c not in out:
            out[c] = None
    return out[cols]


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    frames, status = [], {}

    # UN SDG database (national)
    try:
        pages = un_sdg.load_pages()
        df = un_sdg.parse_observations(pages, un_sdg.series_releases())
        frames.append(df)
        status["UN_SDG_API"] = {"status": "loaded", "pages": len(pages),
                                "records_in_api": int(pages[0][0]["totalElements"]),
                                "repeats_merged": int(df.attrs.get("repeats_merged", 0)),
                                "unique_observations": int(len(df)),
                                "note": "Series linked to several SDG indicators are returned once per indicator; "
                                        "identical copies are merged."}
    except (FileNotFoundError, un_sdg.IncompleteDownload) as e:
        status["UN_SDG_API"] = {"status": "not available", "detail": str(e)}

    # MoSPI NIF progress report (national time series)
    not_parsed = []
    for source_id, res in mospi.load_all().items():
        status[source_id] = res["status"]
        not_parsed += [{"source_id": source_id, **s} for s in res.get("skipped", [])]
        if res["data"] is not None and not res["data"].empty:
            frames.append(res["data"])

    districts = pd.DataFrame()
    for source_id, res in nfhs.load_all().items():
        status[source_id] = {k: v for k, v in res["status"].items() if k != "problems"}
        not_parsed += [{"source_id": source_id, "code": p["file"], "reason": p["problem"],
                        "kind": p.get("kind", "")} for p in res["status"].get("problems", [])]
        if res["data"] is not None and not res["data"].empty:
            frames.append(res["data"])
            districts = res["districts"] if res.get("districts") is not None else _districts_from(res["data"])

    obs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not obs.empty:
        obs["goal"] = pd.to_numeric(obs["goal"], errors="coerce").astype("Int64")
        obs["year"] = pd.to_numeric(obs["year"], errors="coerce").astype("Int64")
        obs = obs.sort_values(["goal", "indicator_code", "series_code", "geo_id", "year", "dimensions"],
                              kind="stable").reset_index(drop=True)

    scores, score_status = niti.load_scores()
    status.update(score_status)

    context = district_context(districts, status, not_parsed)

    report = validate(obs, scores, districts)

    indicators = un_sdg.parse_metadata()
    cov = coverage(obs)
    if not indicators.empty:
        have = set(obs["series_code"]) if not obs.empty else set()
        indicators["has_india_data"] = indicators["series_code"].isin(have)

    # Write outputs
    obs.to_csv(OUT / "observations.csv", index=False)
    pd.DataFrame(not_parsed, columns=["source_id", "code", "goal", "target", "name", "source", "periodicity", "page",
                                      "reason", "kind"]).to_csv(OUT / "not_parsed.csv", index=False)
    cov.to_csv(OUT / "coverage.csv", index=False)
    indicators.to_csv(OUT / "indicators.csv", index=False)
    scores.to_csv(OUT / "index_scores.csv", index=False)
    context.to_csv(OUT / "district_context.csv", index=False)
    geos = geography.registry().assign(parent_geo_id="")
    if not districts.empty:
        geos = pd.concat([geos, districts[["geo_id", "geography", "geo_level", "parent_geo_id"]]], ignore_index=True)
    geos.to_csv(OUT / "geographies.csv", index=False)
    src = pd.DataFrame(config.SOURCES)
    src["status"] = src["source_id"].map(lambda s: json.dumps(status.get(s, {"status": "not used"})))
    src.to_csv(OUT / "sources.csv", index=False)

    manifest = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "totals": summarise(obs),
        "by_source": {s: summarise(g) for s, g in obs.groupby("source_id")} if not obs.empty else {},
        "index_scores": {"rows": int(len(scores)),
                         "editions": sorted(scores["edition"].unique().tolist()) if not scores.empty else []},
        "source_status": status,
        "validation": report,
        "software": _versions(),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    write_coverage_report(obs, indicators, scores, manifest, not_parsed)
    return manifest


def write_coverage_report(obs: pd.DataFrame, indicators: pd.DataFrame, scores: pd.DataFrame, manifest: dict,
                          not_parsed: list | None = None) -> None:
    """docs/COVERAGE.md: what the current build actually contains, generated from the data."""
    t = manifest["totals"]
    lines = ["# Data coverage", "", f"Generated by `python -m sdg_india build` on {manifest['built_at'][:10]}. "
             "Every number below is computed from the processed data.", ""]
    if t.get("observations"):
        lines += ["## Totals", "",
                  "| Measure | Value |", "|---|---|",
                  f"| Observations with a value | {t['observations']:,} |",
                  "| Publisher's 'not available' markers (not counted as observations) | "
                  f"{t['not_available_markers']:,} |",
                  f"| Indicators with India data | {t['indicators']} |",
                  f"| Data series with India data | {t['series']} |",
                  f"| Goals with data | {len(t['goals_covered'])} of 17 |",
                  f"| Geographies | {t['geographies']} (India, national) |",
                  f"| Earliest / latest observation year | {t['earliest_year']} / {t['latest_year']} |",
                  f"| Observations before 2015 | {t['observations_before_2015']:,} |", ""]
        lines += ["## By source", "", "| Source | Observations | Indicators | Series | Years | Before 2015 |",
                  "|---|---|---|---|---|---|"]
        for sid, s in manifest["by_source"].items():
            lines.append(f"| {sid} | {s['observations']:,} | {s['indicators']} | {s['series']} "
                         f"| {s['earliest_year']}–{s['latest_year']} | {s['observations_before_2015']:,} |")
        lines += ["", "UN indicator codes are global SDG codes; MoSPI codes are India's national NIF codes, which "
                  "follow the same target numbering but are different indicators. The total indicator count above "
                  "counts a code once even when both sources use it.", ""]
        real = obs[obs["value_status"] != "not_available"]
        ex = explode_by_indicator(real)
        g = ex.groupby("goal").agg(indicators=("indicator_code", "nunique"), series=("series_code", "nunique"),
                                   observations=("obs_id", "nunique"), first=("year", "min"), latest=("year", "max"))
        if not indicators.empty:
            g = g.join(indicators.drop_duplicates(["goal", "indicator_code"]).groupby("goal")["indicator_code"]
                       .nunique().rename("un_list"))
        lines += ["## By goal", "", "Series filed under several goals are counted under each.", "",
                  "| Goal | Indicators with data / in UN list | Series | Observations | Years |",
                  "|---|---|---|---|---|"]
        for goal, r in g.iterrows():
            lines.append(f"| {goal}. {config.GOALS[int(goal)]} | {r.indicators} / {r.get('un_list', '')} "
                         f"| {r.series} | {r.observations:,} | {r['first']}–{r['latest']} |")
        city = real[real["dimensions"].str.contains('"Cities"', regex=False)]
        if len(city):
            n = city["dimensions"].map(lambda d: json.loads(d).get("Cities")).nunique()
            lines += ["", f"City-level breakdowns: {len(city)} observations for {n} cities in "
                          f"{city['series_code'].nunique()} urban series ({city['year'].min()}–{city['year'].max()})."]
    else:
        lines += ["No observations are loaded in this build."]
    if not scores.empty:
        sub = scores["geo_level"] != "national"
        n_state = int(((scores["goal"] == 0) & sub).sum())
        n_nat = int(((scores["goal"] == 0) & ~sub).sum())
        editions = ", ".join(sorted(scores.loc[sub, "edition"].unique()))
        lines += ["", "## NITI Aayog SDG India Index (composite scores, kept separate)", "",
                  f"{len(scores)} published index values: {n_state} State/UT composite scores ({editions}), "
                  f"{n_nat} national composite scores and {int((scores['goal'] > 0).sum())} national goal scores. "
                  f"{int(scores['verification'].astype(str).str.startswith('verified').sum())} are verified against "
                  "the report."]
    dist = obs[obs["geo_level"] == "district"]
    if len(dist):
        nd = dist.drop_duplicates("obs_id")
        n_states = nd["geo_id"].str.rsplit(".", n=1).str[0].nunique()
        lines += ["", "## District data (NFHS District Fact Sheets)", "",
                  f"{nd['geo_id'].nunique()} districts in {n_states} States/UTs, {nd['series_code'].nunique()} "
                  f"indicators linked to {nd['goal'].nunique()} goals, {len(nd)} rows "
                  f"({int((nd['value_status'] == 'numeric').sum())} numeric, "
                  f"{int((nd['value_status'] == 'not_available').sum())} published as 'na' or '*'). "
                  "Rounds: NFHS-5 (2019-21) and NFHS-4 (2015-16)."]
    np_all = pd.DataFrame(not_parsed or [])
    nfhs_np = np_all[np_all["source_id"] == "NFHS5_DISTRICTS"] if len(np_all) else np_all
    if len(nfhs_np):
        lines += ["", f"District fact sheet notes ({len(nfhs_np)}):", ""]
        lines += [f"- `{r.code}`: {r.reason}" for r in nfhs_np.itertuples()]
    not_parsed = [r for r in (not_parsed or []) if r.get("source_id") == "MOSPI_NIF_2025"]
    if not_parsed:
        np_ = pd.DataFrame(not_parsed)
        lines += ["", "## MoSPI indicators not parsed", "",
                  f"{len(np_)} national indicators in the MoSPI report's Data Snapshot were not turned into "
                  "observations, so that no value is guessed:", "", "| Reason | Indicators |", "|---|---|"]
        for reason, n in np_["reason"].str.replace(r" \(e\.g\..*", "", regex=True).value_counts().items():
            lines.append(f"| {reason} | {n} |")
        lines += ["", "The full list with page numbers is in `data/processed/not_parsed.csv`."]
    lines += ["", "## Source status", ""]
    for sid, st_ in manifest["source_status"].items():
        lines.append(f"- **{sid}**: {st_.get('status')}" + (f" ({st_['detail']})" if st_.get("detail") else ""))
    (config.ROOT / "docs" / "COVERAGE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
