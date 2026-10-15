"""NITI Aayog SDG India Index: published composite scores for India and every State/UT.

These are composite index scores (0-100), built by NITI Aayog from normalised, weighted
indicators. They are stored in their own table (``index_scores.csv``) and never mixed with
raw indicator observations.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .. import config
from ..http import DownloadError, download, pdf_problem, session

SOURCE_ID = "NITI_SDGII_2023_24"
RAW_DIR = config.RAW / "niti"
PDF = RAW_DIR / "SDG_India_Index_2023-24.pdf"
SCORES = config.REFERENCE / "niti_index_scores.csv"


def fetch(refresh: bool = False) -> Path:
    path = download(config.SOURCE_BY_ID[SOURCE_ID]["url"], PDF, refresh=refresh or bool(pdf_problem(PDF)),
                    sess=session(), timeout=300, min_bytes=100_000)
    problem = pdf_problem(path)
    if problem:
        raise DownloadError(f"{path.name}: {problem}")
    return path


def load_scores() -> tuple[pd.DataFrame, dict]:
    if not SCORES.exists():
        return pd.DataFrame(), {SOURCE_ID: {"status": "not available", "detail": f"{SCORES.name} missing"}}
    df = pd.read_csv(SCORES)
    verified = int(df["verification"].astype(str).str.startswith("verified").sum())
    return df, {SOURCE_ID: {"status": "loaded", "rows": int(len(df)), "verified_rows": verified,
                            "pdf_available": PDF.exists()}}
