"""NFHS-5 District Fact Sheets (Ministry of Health and Family Welfare / IIPS), 2019-21, with NFHS-4 (2015-16).

Each district fact sheet is a text PDF with 104 numbered "Key Indicators" and two columns:
NFHS-5 and NFHS-4. This module parses every fact sheet in ``data/raw/nfhs5_districts/<state>/``.

Only indicators with a clear SDG counterpart are loaded (``SDG_MAP``); each mapping states
whether the NFHS measure is the same as a national NIF indicator or only related to an SDG
target. Published markers are kept: "na" (not available) and "*" (suppressed, fewer than 25
cases) are not-available markers; values in parentheses (based on 25-49 cases) are kept with a
footnote saying so.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from .. import config, geography
from ..http import sha256

SOURCE_ID = "NFHS5_DISTRICTS"
RAW_DIR = config.RAW / "nfhs5_districts"
EXTRACT = config.REFERENCE / "nfhs5_districts_extract.csv"
MIRROR = "https://github.com/SaiSiddhardhaKalla/NFHS/tree/main/pdfs"
OFFICIAL = "http://rchiips.org/nfhs/districtfactsheet_NFHS-5.shtml"

# NFHS indicator number -> (goal, target, relation, NIF code or "", short label, unit)
# relation: "same" = same measure as the national NIF indicator; "related" = related to the SDG target.
SDG_MAP = {
    4: (5, "5.1", "related", "5.1.3", "Sex ratio at birth (females per 1,000 males)", "per 1,000 males"),
    5: (16, "16.9", "related", "", "Children under 5 whose birth was registered", "%"),
    6: (17, "17.19", "related", "", "Deaths in the last 3 years registered", "%"),
    7: (7, "7.1", "same", "7.1.1", "Population living in households with electricity", "%"),
    8: (6, "6.1", "related", "", "Population with an improved drinking-water source", "%"),
    9: (6, "6.2", "related", "", "Population using an improved sanitation facility", "%"),
    10: (7, "7.1", "related", "7.1.2", "Households using clean fuel for cooking", "%"),
    12: (3, "3.8", "related", "", "Households with a member covered by health insurance/financing", "%"),
    13: (4, "4.2", "related", "", "Children age 5 attending pre-primary school", "%"),
    14: (4, "4.6", "related", "", "Women (15-49) who are literate", "%"),
    16: (5, "5.3", "same", "5.3.1", "Women age 20-24 married before age 18", "%"),
    18: (3, "3.7", "related", "", "Women age 15-19 already mothers or pregnant", "%"),
    21: (3, "3.7", "same", "3.7.4", "Currently married women (15-49) using a modern family planning method", "%"),
    28: (5, "5.6", "same", "5.6.1", "Total unmet need for family planning (currently married women 15-49)", "%"),
    33: (3, "3.1", "related", "", "Mothers who had at least 4 antenatal care visits", "%"),
    42: (3, "3.1", "related", "", "Institutional births", "%"),
    45: (3, "3.1", "related", "", "Births attended by skilled health personnel", "%"),
    49: (3, "3.b", "related", "", "Children 12-23 months fully vaccinated (card or mother's recall)", "%"),
    53: (3, "3.b", "related", "", "Children 12-23 months with 3 doses of penta or DPT vaccine", "%"),
    55: (3, "3.b", "related", "", "Children 24-35 months with a second dose of measles-containing vaccine", "%"),
    73: (2, "2.2", "same", "2.2.1", "Children under 5 who are stunted (height-for-age)", "%"),
    74: (2, "2.2", "related", "2.2.2", "Children under 5 who are wasted (weight-for-height)", "%"),
    76: (2, "2.2", "related", "", "Children under 5 who are underweight (weight-for-age)", "%"),
    77: (2, "2.2", "related", "2.2.2", "Children under 5 who are overweight (weight-for-height)", "%"),
    78: (2, "2.2", "same", "2.2.4", "Women whose Body Mass Index is below normal", "%"),
    81: (2, "2.2", "related", "", "Children 6-59 months who are anaemic", "%"),
    83: (2, "2.2", "related", "2.2.3", "Pregnant women age 15-49 who are anaemic", "%"),
    84: (2, "2.2", "related", "2.2.3", "All women age 15-49 who are anaemic", "%"),
    94: (3, "3.4", "related", "3.8.4", "Women 15+ with elevated blood pressure or taking medicine", "%"),
    97: (3, "3.4", "related", "3.8.4", "Men 15+ with elevated blood pressure or taking medicine", "%"),
    101: (3, "3.a", "related", "3.a.1", "Women age 15+ who use any kind of tobacco", "%"),
    102: (3, "3.a", "related", "3.a.1", "Men age 15+ who use any kind of tobacco", "%"),
    103: (3, "3.5", "related", "3.5.3", "Women age 15+ who consume alcohol", "%"),
    104: (3, "3.5", "related", "3.5.3", "Men age 15+ who consume alcohol", "%"),
}

ROW2 = re.compile(r"^\s*(\d{1,3})\.\s+(.*?)\s{2,}(\S+)\s{2,}(\S+)\s*$")
ROW1 = re.compile(r"^\s*(\d{1,3})\.\s+(.*?)\s{2,}(\S+)\s*$")
START = re.compile(r"^\s*(\d{1,3})\.\s+(\S.*)$")
TITLE = re.compile(r"^\s*(.+?),\s*(.+?)\s+[-–]\s+Key Indicators\s*$")
GATHERED = re.compile(r"\bIn ([^,.;]+?), information was gathered")
ROUND = re.compile(r"^\s*Indicators\s+\((20\d\d-\d\d)\)(?:\s+\((20\d\d-\d\d)\))?\s*$")
NA = {"na", "*", "-", "NA"}


def page_text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True,
                          check=True).stdout.decode("utf-8", errors="replace")


def cell(raw: str) -> tuple[float | None, str, str]:
    t = raw.strip()
    if t in NA:
        return None, "not_available", ("* = percentage not shown, based on fewer than 25 unweighted cases"
                                        if t == "*" else "")
    note = ""
    m = re.fullmatch(r"\((.+)\)", t)
    if m:
        t, note = m.group(1), "( ) = based on 25-49 unweighted cases"
    if re.fullmatch(r"-?\d{1,3}(,\d{2,3})*(\.\d+)?|-?\d+(\.\d+)?", t):
        return float(t.replace(",", "")), "numeric", note
    return None, "text", note


def parse_sheet(text: str) -> dict:
    """District, state, survey periods and {indicator number: (name, [raw values])}.

    Districts formed after NFHS-4 have only the NFHS-5 column; their NFHS-4 values are absent, not empty.
    """
    district = state = None
    rounds, pending, order = None, None, []
    lines = text.splitlines()
    # district name from the cover page ("District Fact Sheet" / <district> / <state>), checked against the
    # sentence "In <district>, information was gathered ..." later in the same document
    for i, line in enumerate(lines[:40]):
        if line.strip() == "District Fact Sheet":
            rest = [x.strip() for x in lines[i + 1:i + 6] if x.strip()]
            cover = rest[0] if rest else None
            said = GATHERED.search(re.sub(r"\s+", " ", text))
            if cover and said and said.group(1).strip() == cover:
                district = cover
            break
    for line in lines:
        if state is None and (m := TITLE.match(line)):
            district = district or m.group(1).strip()
            state = m.group(2).strip()
            continue
        if rounds is None and (m := ROUND.match(line)):
            rounds = tuple(r for r in m.groups() if r)
            continue
        if rounds is None:
            continue
        row = ROW2 if len(rounds) == 2 else ROW1
        m = row.match(line)
        if m and 1 <= int(m.group(1)) <= 110:
            order.append((int(m.group(1)), m.group(2).strip(), [g.strip() for g in m.groups()[2:]]))
            pending = None
            continue
        m = START.match(line)
        if m and 1 <= int(m.group(1)) <= 110:
            pending = (int(m.group(1)), m.group(2).strip())
            order.append((pending[0], pending[1], None))          # name seen, values not (yet) on this line
            continue
        if pending:
            cont = (re.match(r"^\s+(.*?)\s{2,}(\S+)\s{2,}(\S+)\s*$", line) if len(rounds) == 2
                    else re.match(r"^\s+(.*?)\s{2,}(\S+)\s*$", line))
            if cont:
                vals = [g.strip() for g in cont.groups()[1:]]
                order[-1] = (pending[0], pending[1] + " " + cont.group(1).strip(), vals)
                pending = None
    return {"district": district, "state": state, "rounds": rounds, "order": order}


def norm_name(name: str) -> str:
    """Indicator name without footnote markers, punctuation or spacing differences."""
    t = re.sub(r"\(%\)|\(Rs\.\)", " ", name)
    t = re.sub(r"(?<=[A-Za-z\)])\s?\d{1,2}(?:\s?,\s?\d{1,2})*(?=\s|$)", " ", t)     # footnote numbers
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def assign_numbers(order: list, canon: dict[str, list[int]]) -> tuple[dict, list[str]]:
    """Map each row to the standard indicator number by its name; the k-th occurrence of a name that
    appears several times (e.g. blood pressure for women, then men) takes the k-th standard number."""
    seen: dict[str, int] = {}
    rows, notes = {}, []
    for printed, name, vals in order:
        key = norm_name(name)
        nums = canon.get(key)
        if not nums:
            notes.append(f"unrecognised indicator name at printed number {printed}")
            continue
        k = seen.get(key, 0)
        seen[key] = k + 1
        if k >= len(nums):
            notes.append(f"indicator name repeated more often than expected at printed number {printed}")
            continue
        n = nums[k]
        if n != printed:
            notes.append(f"printed number {printed} is indicator {n} by its name")
        if vals is not None:
            rows[n] = (name, vals)
    return rows, notes


def state_geo(folder: str, printed: str | None) -> str | None:
    special = {"nct_of_delhi": "Delhi", "dadra_nagar_haveli_daman_diu": "Dadra and Nagar Haveli and Daman and Diu",
               "andaman_nicobar_island": "Andaman and Nicobar Islands", "jammu_kashmir": "Jammu and Kashmir"}
    return geography.resolve(printed or "") or geography.resolve(special.get(folder, folder.replace("_", " ")))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def load_all() -> dict:
    pdfs = sorted(RAW_DIR.glob("*/*.pdf"))
    if not pdfs or not shutil.which("pdftotext"):
        reason = "fact sheets not downloaded" if not pdfs else "pdftotext (Poppler) not installed"
        if EXTRACT.exists():
            from ..io import read_observations
            df = read_observations(EXTRACT)
            return {SOURCE_ID: {"status": {"status": "loaded from verified extract", "detail": reason,
                                           "rows": int(len(df))}, "data": df, "districts": None}}
        return {SOURCE_ID: {"status": {"status": "not available", "detail": reason}, "data": None,
                            "districts": None}}
    out, districts, problems = [], [], []
    sheets = [(pdf, parse_sheet(page_text(pdf))) for pdf in pdfs]
    # standard name of each indicator number: the most common name printed against it across all sheets
    votes: dict[int, dict[str, int]] = {}
    for _, sh in sheets:
        for printed, name, _v in sh["order"]:
            votes.setdefault(printed, {}).setdefault(norm_name(name), 0)
            votes[printed][norm_name(name)] += 1
    canon: dict[str, list[int]] = {}
    for n in sorted(votes):
        if n <= 104:
            best = max(votes[n].items(), key=lambda kv: kv[1])[0]
            canon.setdefault(best, []).append(n)
    renumbered = 0
    for pdf, sheet in sheets:
        sheet["rows"], notes = assign_numbers(sheet["order"], canon)
        if any(x.startswith("printed number") for x in notes):
            renumbered += 1
            problems.append({"file": f"{pdf.parent.name}/{pdf.name}", "problem": "numbering in the source differs: "
                             + "; ".join(x for x in notes if x.startswith("printed number"))[:200], "kind": "note"})
        st_geo = state_geo(pdf.parent.name, sheet["state"])
        if not sheet["district"] or st_geo is None or not sheet["rounds"]:
            problems.append({"file": f"{pdf.parent.name}/{pdf.name}", "problem": "title, state or survey years "
                             "not found"})
            continue
        missing = [n for n in SDG_MAP if n not in sheet["rows"]]
        if missing:
            problems.append({"file": f"{pdf.parent.name}/{pdf.name}", "problem": f"values not readable for "
                             f"indicators {missing} (values split across lines out of column order)",
                             "kind": "skipped"})
        geo_id = f"{st_geo}.{slug(sheet['district'])}"
        districts.append({"geo_id": geo_id, "geography": sheet["district"], "geo_level": "district",
                          "parent_geo_id": st_geo, "state": geography.name_of(st_geo),
                          "source_file": f"{pdf.parent.name}/{pdf.name}"})
        digest = sha256(pdf)
        for n, (goal, target, relation, nif, label, unit) in SDG_MAP.items():
            if n not in sheet["rows"]:
                continue
            name, vals = sheet["rows"][n]
            for k, (rnd, raw) in enumerate(zip(sheet["rounds"], vals, strict=True)):
                v, status, note = cell(raw)
                survey = "NFHS-5" if k == 0 else "NFHS-4"
                clean_name = re.sub(r"\s+", " ", name)
                notes = [f"NFHS indicator {n}: {clean_name}",
                         f"Relation to SDG: {relation}" + (f" (NIF {nif})" if nif else f" (target {target})")]
                if note:
                    notes.append(note)
                out.append({
                    "source_id": SOURCE_ID, "goal": goal, "target": target,
                    "indicator_code": nif or target, "indicator_codes_all": nif or f"{target}.0",
                    "goals_all": str(goal), "series_code": f"NFHS_D{n:03d}",
                    "series_description": f"[NFHS district] {label}",
                    "geo_id": geo_id, "geography": sheet["district"], "geo_level": "district",
                    "year": int(rnd[:4]), "time_period": f"{survey} {rnd}",
                    "value": v, "value_raw": raw, "value_status": status, "unit": unit, "unit_multiplier": "",
                    "nature": "", "reporting_type": "", "dimensions": json.dumps({}, sort_keys=True),
                    "lower_bound": None, "upper_bound": None, "base_period": "",
                    "original_source": "National Family Health Survey (NFHS), MoHFW / IIPS",
                    "footnotes": " | ".join(notes), "release": f"{survey} District Fact Sheet",
                    "source_url": OFFICIAL, "raw_file": f"nfhs5_districts/{pdf.parent.name}/{pdf.name}",
                    "raw_sha256": digest, "retrieved_at": "", "report_page": None, "headline": True,
                })
    df = pd.DataFrame(out)
    if not df.empty:
        key = df[["source_id", "series_code", "geo_id", "time_period"]].astype(str).agg("|".join, axis=1)
        df.insert(0, "obs_id", key.map(lambda k: hashlib.sha1(k.encode()).hexdigest()[:16]))
        EXTRACT.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(EXTRACT, index=False)
    dist = pd.DataFrame(districts)
    status = {"status": "loaded", "fact_sheets": len(pdfs), "districts": int(dist["geo_id"].nunique()) if len(dist)
              else 0, "states_and_uts": int(dist["parent_geo_id"].nunique()) if len(dist) else 0,
              "indicators_mapped": len(SDG_MAP), "rows": int(len(df)), "problems": problems,
              "sheets_with_source_numbering_errors_corrected_by_name": renumbered,
              "problem_count": len(problems)}
    return {SOURCE_ID: {"status": status, "data": df, "districts": dist}}
