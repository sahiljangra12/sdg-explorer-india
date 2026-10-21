"""NITI Aayog, List of 112 Aspirational Districts (Aspirational Districts Programme).

A yes/no attribute of a district, used only as a filter. Districts created after NFHS-5
(2019-21) cannot be linked to an NFHS district and are listed as unmatched; no parent district
is labelled aspirational in their place.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .. import config
from ..http import sha256
from .mpi import match_districts

SOURCE_ID = "NITI_ASPIRATIONAL"
URL = "https://www.niti.gov.in/sites/default/files/2023-07/List-of-112-Aspirational-Districts%20%281%29.pdf"
PDF = config.RAW / "niti_aspirational" / "List-of-112-Aspirational-Districts.pdf"
EXTRACT = config.REFERENCE / "niti_aspirational_districts.csv"
ALIASES = {  # (state as published, district as published) -> geo_id, reviewed by hand
    ("Andhra Pradesh", "Y.S.R. Kadapa"): "IN.AP.y-s-r",
    ("Bihar", "Purnea"): "IN.BR.purnia",
    ("Chhattisgarh", "Kanker"): "IN.CG.uttar-bastar-kanker",
    ("Chhattisgarh", "Kondagaon"): "IN.CG.kodagaon",
    ("Jharkhand", "Hazaribag"): "IN.JH.hazaribagh",
    ("Madhya Pradesh", "Khandwa"): "IN.MP.khandwa-east-nimar",
    ("Punjab", "Ferozepur"): "IN.PB.firozpur",
    ("Rajasthan", "Dholpur"): "IN.RJ.dhaulpur",
    ("Telangana", "Asifabad"): "IN.TS.komaram-bheem-asifabad",
    ("Telangana", "Bhupalpally"): "IN.TS.jayashankar-bhupalapally",
    ("Uttarakhand", "Udham Singh Nagar"): "IN.UK.udam-singh-nagar",
}


def fetch(refresh: bool = False) -> Path:
    from ..http import DownloadError, download, pdf_problem, session

    path = download(URL, PDF, refresh=refresh or bool(pdf_problem(PDF)), sess=session(), timeout=120,
                    min_bytes=10_000)
    problem = pdf_problem(path)
    if problem:
        raise DownloadError(f"{path.name}: {problem}")
    return path


def extract(pdf_path: Path = PDF) -> pd.DataFrame:
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        rows = [r for p in pdf.pages for t in p.extract_tables() for r in t if r and (r[0] or "").strip().isdigit()]
    df = pd.DataFrame([[int(r[0]), re.sub(r"\s+", " ", r[1].strip()), re.sub(r"\s+", " ", r[2].strip())]
                       for r in rows], columns=["s_no", "state", "district"])
    if df["s_no"].tolist() != list(range(1, len(df) + 1)):
        raise ValueError("Aspirational Districts list: serial numbers are not 1..n; the table was not read cleanly")
    df.insert(0, "raw_sha256", sha256(pdf_path))
    return df


def load(districts: pd.DataFrame) -> dict:
    if PDF.exists():
        old = pd.read_csv(EXTRACT, dtype=str) if EXTRACT.exists() else pd.DataFrame()
        if old.empty or old["raw_sha256"].iloc[0] != sha256(PDF):
            extract(PDF).to_csv(EXTRACT, index=False)
    if not EXTRACT.exists():
        return {"data": pd.DataFrame(), "skipped": [], "status": {"status": "not available"}}
    df = pd.read_csv(EXTRACT, dtype=str, keep_default_na=False)
    geo = match_districts(df, districts) if len(districts) else pd.Series([None] * len(df))
    df["geo_id"] = [g or ALIASES.get((s, d)) for g, s, d in zip(geo, df["state"], df["district"], strict=True)]
    un = df[df["geo_id"].isna()]
    skipped = [{"state": r.state, "district": r.district,
                "reason": "district created after NFHS-5 or not in the NFHS fact sheets; not linked to any district"}
               for r in un.itertuples()]
    return {"data": df, "skipped": skipped,
            "status": {"status": "loaded", "listed": int(len(df)), "matched_districts": int(df["geo_id"].notna().sum()),
                       "unmatched": int(len(un)), "pdf_available": PDF.exists()}}
