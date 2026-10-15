"""Read processed tables without pandas reinterpreting published text.

pandas turns strings such as "NaN", "NA" or "N/A" into missing values by default. Published
raw values must survive a round trip through CSV exactly, so text columns are read verbatim
and only the numeric columns are converted.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

NUMERIC = ["value", "lower_bound", "upper_bound"]
INTEGER = ["goal", "year"]


def read_observations(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size <= 2:
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[], low_memory=False)
    if df.empty:
        return df
    for c in NUMERIC:
        if c in df:
            df[c] = pd.to_numeric(df[c].replace("", None), errors="coerce")
    for c in INTEGER:
        if c in df:
            df[c] = pd.to_numeric(df[c].replace("", None), errors="coerce").astype("Int64")
    if "headline" in df:
        df["headline"] = df["headline"].str.lower().eq("true")
    return df


def explode_by_indicator(obs: pd.DataFrame) -> pd.DataFrame:
    """One row per observation and linked indicator, with the goal of that indicator.

    A series filed under several indicators (e.g. disaster deaths under 1.5.1, 11.5.1 and 13.1.1)
    then appears under every goal it belongs to. Use the unexploded table for counting observations.
    """
    if obs.empty:
        return obs
    out = obs.assign(indicator_code=obs["indicator_codes_all"].str.split(";")).explode("indicator_code")
    out["goal"] = pd.to_numeric(out["indicator_code"].str.split(".").str[0], errors="coerce").astype("Int64")
    return out.reset_index(drop=True)
