"""Validation rules for the processed observation table.

Errors stop the build. Warnings are written to the validation report for review.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from . import config, geography

REQUIRED = ["obs_id", "source_id", "goal", "indicator_code", "series_code", "geo_id", "geography", "year",
            "time_period", "value_raw", "unit", "source_url", "raw_file", "raw_sha256"]


class ValidationError(RuntimeError):
    pass


def validate(obs: pd.DataFrame, index_scores: pd.DataFrame | None = None,
             districts: pd.DataFrame | None = None) -> dict:
    errors, warnings = [], []
    if obs.empty:
        return {"rows": 0, "errors": [], "warnings": ["No observations loaded."]}

    missing_cols = [c for c in REQUIRED if c not in obs.columns]
    if missing_cols:
        raise ValidationError(f"Missing columns: {missing_cols}")

    for col in ["obs_id", "source_id", "series_code", "geo_id", "year", "source_url", "raw_sha256"]:
        n = int(obs[col].isna().sum() + (obs[col].astype(str).str.strip() == "").sum())
        if n:
            errors.append(f"{n} rows have an empty '{col}'.")

    dup = int(obs["obs_id"].duplicated().sum())
    if dup:
        errors.append(f"{dup} duplicate observation ids (same series, geography, period and breakdown).")

    goals = pd.to_numeric(obs["goal"], errors="coerce")
    if (~goals.dropna().between(1, 17)).any():
        errors.append("Goal numbers outside 1-17.")
    if goals.isna().any():
        warnings.append(f"{int(goals.isna().sum())} rows have no goal code.")

    years = pd.to_numeric(obs["year"], errors="coerce")
    bad_years = obs[(years < 1950) | (years > date.today().year + 1)]
    if len(bad_years):
        errors.append(f"{len(bad_years)} rows have implausible years.")

    known = set(geography.registry()["geo_id"])
    if districts is not None and not districts.empty:
        known |= set(districts["geo_id"])
        orphans = set(districts["parent_geo_id"]) - set(geography.registry()["geo_id"])
        if orphans:
            errors.append(f"Districts with unknown parent State/UT: {sorted(orphans)[:5]}")
    unknown = sorted(set(obs["geo_id"]) - known)
    if unknown:
        errors.append(f"Unknown geographies: {unknown[:10]}")

    kinds = {s["source_id"]: s["kind"] for s in config.SOURCES}
    composite = sorted({s for s in obs["source_id"].unique() if kinds.get(s) == "composite_index"})
    if composite:
        errors.append(f"Composite index sources found in the observation table: {composite}")

    # A missing number must be explained by what the publisher wrote (a text value or a not-available marker)
    status = obs["value_status"] if "value_status" in obs else pd.Series("numeric", index=obs.index)
    unexplained = obs["value"].isna() & (status == "numeric")
    unexplained |= obs["value"].isna() & (obs["value_raw"].astype(str).str.strip() == "") & (status != "not_available")
    if unexplained.any():
        errors.append(f"{int(unexplained.sum())} rows have neither a numeric value nor a published raw value.")
    if (obs["value"].notna() & (status != "numeric")).any():
        errors.append("Rows marked as text or not available carry a numeric value.")

    na = int((status == "not_available").sum())
    if na:
        warnings.append(f"{na} records are the publisher's own 'not available' markers (e.g. 'NaN = Not Available'). "
                        "They are kept for the missing-data analysis and are not counted as observations.")
    txt = obs.loc[status == "text", "value_raw"]
    if len(txt):
        warnings.append(f"{len(txt)} values are published as text and kept as text, not converted "
                        f"(most common: {txt.value_counts().head(5).to_dict()}).")

    pct = obs["unit"].astype(str).str.upper().eq("PERCENT") & obs["value"].notna()
    out_of_range = obs[pct & ~obs["value"].between(0, 100)]
    if len(out_of_range):
        warnings.append(f"{len(out_of_range)} percentage values fall outside 0-100 (series: "
                        f"{sorted(out_of_range['series_code'].unique())[:8]}); check the series definitions.")

    if index_scores is not None and not index_scores.empty:
        if (~pd.to_numeric(index_scores["score"], errors="coerce").between(0, 100)).any():
            errors.append("Composite index scores outside 0-100.")

    report = {"rows": int(len(obs)), "errors": errors, "warnings": warnings}
    if errors:
        raise ValidationError("; ".join(errors))
    return report
