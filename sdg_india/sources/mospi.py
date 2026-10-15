"""MoSPI Sustainable Development Goals: National Indicator Framework (NIF) Progress Report, 2025.

The report's "Data Snapshot" section has one small table per national indicator: a period
column and one or more value columns. This module reads the PDF's text layer with the
column layout preserved (``pdftotext -layout``, or pdfplumber as a fallback) and parses those
tables with strict rules:

* A table is parsed only if its header is on one line, its columns can be split
  unambiguously, and every data row has exactly one value per column. Anything else is
  listed as "not parsed" in the coverage report rather than guessed.
* Numbers keep the published precision. Indian digit grouping ("1,09,085") and stray spaces
  inside numbers ("277 .0865") are normalised; footnote markers ("66.6614*") are recorded.
* "-" and "NA" are the publisher's not-available markers, kept as such.

Codes are MoSPI's national indicator codes (for example 1.2.1), which are numbered by SDG
target but are not the same as the UN global indicator codes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from .. import config
from ..http import DownloadError, download, pdf_problem, read_meta, session, sha256

SOURCE_ID = "MOSPI_NIF_2025"
RAW_DIR = config.RAW / "mospi"
PDF = RAW_DIR / "SDG_NIF_Progress_Report_2025.pdf"
# Verified extract kept with the project so the data survive if the 37 MB PDF is not downloaded
EXTRACT = config.REFERENCE / "mospi_nif_2025_extract.csv"
EXTRACT_SKIPPED = config.REFERENCE / "mospi_nif_2025_not_parsed.csv"
EXTRACT_STATUS = config.REFERENCE / "mospi_nif_2025_extract_status.json"

BLOCK = re.compile(r"^\s*(\d{1,2})\s+(\d{1,2}\.[0-9a-z]{1,2}\.\d{1,2}(?:\([a-z]\))?)\s*:\s*(.*)$")
TARGET = re.compile(r"^\s*Target\s+(\d{1,2}\.[0-9a-z]{1,2})\s*:")
GOAL = re.compile(r"^\s*Goal\s+(\d{1,2})\s*:")
PERIOD = re.compile(r"^((?:From\s+)?\d{4}(?:-\d{2,4})?(?:\s+to\s+\d{4}(?:-\d{2,4})?)?)$")
NUMBER = re.compile(r"^[-+]?\d{1,3}(?:,\d{2,3})*(?:\.\d+)?$|^[-+]?\d+(?:\.\d+)?$")
NOT_AVAILABLE = {"-", "--", "NA", "N.A.", "n.a.", "N/A"}
PAGE_FURNITURE = re.compile(r"PROGRESS REPORT 2025|DATA SNAPSHOT|^\s*\d+\s*\|?\s*$")


def fetch(refresh: bool = False) -> Path:
    path = download(config.SOURCE_BY_ID[SOURCE_ID]["url"], PDF, refresh=refresh or bool(pdf_problem(PDF)),
                    sess=session(), timeout=300, min_bytes=100_000)
    problem = pdf_problem(path)
    if problem:
        raise DownloadError(f"{path.name}: {problem}")
    return path


# ---------------------------------------------------------------- text extraction
def page_texts(pdf: Path) -> list[str]:
    """Text of every page with the column layout preserved (Poppler's pdftotext -layout).

    The table rules were developed and verified against this engine's layout. Other engines
    space columns differently, so they are not used as a silent substitute.
    """
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, check=True).stdout
    return out.decode("utf-8", errors="replace").split("\f")


def snapshot_pages(pages: list[str]) -> range:
    """PDF page indexes of the Data Snapshot section: from the first 'Goal 1:' heading to the metadata section."""
    start = next(i for i, t in enumerate(pages) if re.search(r"^\s*Goal 1\s*:", t, re.M) and "S.NO." in t)
    end = next(i for i, t in enumerate(pages) if i > start and re.search(r"SDG 1 Metadata", t))
    return range(start, end)


# ---------------------------------------------------------------- value parsing
def clean_number(token: str) -> tuple[float | None, str, str]:
    """Return (value, status, footnote_marker) for a published table cell."""
    t = token.strip()
    marker = ""
    m = re.match(r"^(.*?)([*#@^]+)$", t)
    if m:
        t, marker = m.group(1).strip(), m.group(2)
    if t in NOT_AVAILABLE:
        return None, "not_available", marker
    t2 = re.sub(r"(?<=\d)\s+(?=\.\d)", "", t)           # "277 .0865" -> "277.0865"
    if NUMBER.match(t2):
        return float(t2.replace(",", "")), "numeric", marker
    return None, "text", marker


def start_year(period: str) -> int:
    return int(re.search(r"\d{4}", period).group())


def split_cells(s: str) -> list[str]:
    return [c for c in re.split(r"\s{2,}", s.strip()) if c]


# ---------------------------------------------------------------- table parsing
def _split(line: str, col: int) -> tuple[str, str]:
    """Split a layout line into the indicator-text column and the table column at ``col``.

    The table may start a few characters earlier or later on different pages, so the cut is
    moved to the nearest whitespace within a small window.
    """
    if col <= 0 or len(line) <= col:
        return line.strip(), ""
    for d in range(0, 8):
        for c in (col - d, col + d):
            if 0 < c < len(line) and line[c - 1].isspace():
                return line[:c].strip(), line[c:].strip()
    return line[:col].strip(), line[col:].strip()


def parse_snapshot(pages: list[str], page_range: range) -> tuple[list[dict], list[dict]]:
    """Return (rows, skipped): parsed observations, and indicators that were not parsed with the reason."""
    blocks, goal, target, cur = [], None, None, None
    for pidx in page_range:
        for line in pages[pidx].splitlines():
            if not line.strip() or PAGE_FURNITURE.search(line):
                continue
            if (m := GOAL.match(line)):
                goal, cur = int(m.group(1)), None
                continue
            if (m := TARGET.match(line)):
                target, cur = m.group(1), None
                continue
            if (m := BLOCK.match(line)):
                cur = {"goal": goal, "target": target, "code": m.group(2), "page": pidx + 1,
                       "first": line, "name_start": m.start(3), "lines": []}
                blocks.append(cur)
                continue
            if cur is not None:
                cur["lines"].append(line)

    rows, skipped = [], []
    for b in blocks:
        all_lines = [b["first"]] + b["lines"]
        hdr_i, col = None, -1
        for i, line in enumerate(all_lines):
            m = re.search(r"(?<!\S)Year(?!\S)", line)
            if m and m.start() >= (35 if i else 20):
                hdr_i, col = i, m.start()
                break
        left_parts, right_parts = [], []
        for i, line in enumerate(all_lines):
            lft, rgt = _split(line, col) if hdr_i is not None else (line.strip(), "")
            if i == 0:                                   # drop the "S.No.  code:" prefix from the name
                lft = line[b["name_start"]:col if hdr_i is not None and col > b["name_start"] else None].strip()
            left_parts.append(lft)
            right_parts.append(rgt)
        name, source, periodicity = _describe(left_parts)
        base = {"code": b["code"], "goal": b["goal"] or int(b["code"].split(".")[0]), "target": b["target"],
                "name": name, "source": source, "periodicity": periodicity, "page": b["page"]}
        if hdr_i is None:
            note = " ".join(r for r in right_parts if r) or " ".join(all_lines)
            reason = ("no table: " + ("indicator under development or compilation"
                                       if re.search(r"under (development|compilation)", note, re.I)
                                       else "values published as text or under other indicators"))
            skipped.append({**base, "reason": reason})
            continue
        if any(right_parts[:hdr_i]):
            skipped.append({**base, "reason": "table header spans several lines; columns cannot be split safely"})
            continue
        header = split_cells(right_parts[hdr_i])
        cols = header[1:]
        unit = ""
        if len(cols) == 1:
            mu = re.match(r"^(Value|Rate)\s*(?:\((?:in\s+)?(.+?)\))?$", cols[0])
            if not mu:
                skipped.append({**base, "reason": f"column header not recognised: {cols[0][:40]!r}"})
                continue
            unit, cols = (mu.group(2) or "").strip(), ["Value"]
        if not cols:
            skipped.append({**base, "reason": "header has no value columns"})
            continue
        data, footnotes, bad = [], [], []
        for r in right_parts[hdr_i + 1:]:
            if not r:
                continue
            cells = split_cells(r)
            if cells and PERIOD.match(cells[0]):
                if len(cells) - 1 != len(cols):
                    bad.append(r)
                    continue
                data.append((cells[0], cells[1:]))
            elif r.startswith(("*", "#", "@", "^")):
                footnotes.append(r)
            else:
                bad.append(r)
        periods = [d[0] for d in data]
        if len(set(periods)) != len(periods):
            skipped.append({**base, "reason": "periods repeat within the table (an extra grouping column such as "
                                             "quarter); not parsed to avoid mixing groups"})
            continue
        if len(set(cols)) != len(cols):
            skipped.append({**base, "reason": "column names repeat; columns cannot be told apart"})
            continue
        if bad or not data:
            skipped.append({**base, "reason": "table layout not parseable without guessing"
                                             + (f" (e.g. {bad[0][:50]!r})" if bad else " (no data rows)")})
            continue
        for period, vals in data:
            for colname, raw in zip(cols, vals, strict=True):
                v, status, marker = clean_number(raw)
                rows.append({**base, "period": period, "year": start_year(period), "column": colname,
                             "value": v, "value_raw": raw, "value_status": status, "unit": unit,
                             "footnote": " ".join(footnotes) if marker else ""})
    return rows, skipped


def _describe(left: list[str]) -> tuple[str, str, str]:
    """Indicator name, source and periodicity from the left-hand text of a block."""
    text = " ".join(x for x in left if x)
    text = re.sub(r"\s+", " ", text).strip()
    name, _, rest = text.partition("Source:")
    source, periodicity = rest, ""
    m = re.search(r"/\s*Periodicity\s*:\s*(.+)$", rest)
    if m:
        source, periodicity = rest[:m.start()], m.group(1)
    return name.strip(" ,"), source.strip(" /"), periodicity.strip()


# ---------------------------------------------------------------- observations
def to_observations(rows: list[dict], pdf: Path) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    meta = read_meta(pdf)
    url = config.SOURCE_BY_ID[SOURCE_ID]["url"]
    digest = meta.get("sha256") or sha256(pdf)
    out = []
    for r in rows:
        dims = {} if r["column"] == "Value" else {"Category": r["column"]}
        if r.get("group"):
            dims[r.get("group_name") or "Group"] = r["group"]
        series = f"NIF_{r['code']}"
        notes = [f"Periodicity: {r['periodicity']}"] if r["periodicity"] else []
        if r["footnote"]:
            notes.append(r["footnote"])
        if r.get("parser"):
            notes.append(f"Read from the table's gridlines; column labels checked against the report page "
                         f"({r['parser']})")
        out.append({
            "source_id": SOURCE_ID, "goal": r["goal"], "target": r["target"] or "",
            "indicator_code": r["code"], "indicator_codes_all": r["code"], "goals_all": str(r["goal"]),
            "series_code": series, "series_description": f"[MoSPI NIF {r['code']}] {r['name']}",
            "geo_id": "IN", "geography": "India", "geo_level": "national",
            "year": r["year"], "time_period": r["period"],
            "value": r["value"], "value_raw": r["value_raw"], "value_status": r["value_status"],
            "unit": r["unit"], "unit_multiplier": "", "nature": "", "reporting_type": "",
            "dimensions": json.dumps(dims, ensure_ascii=False, sort_keys=True),
            "lower_bound": None, "upper_bound": None, "base_period": "",
            "original_source": r["source"], "footnotes": " | ".join(notes),
            "release": "NIF Progress Report 2025", "source_url": f"{url}#page={r['page']}",
            "raw_file": f"{pdf.parent.name}/{pdf.name}", "raw_sha256": digest,
            "retrieved_at": meta.get("retrieved_at", ""), "report_page": r["page"],
        })
    df = pd.DataFrame(out)
    key = df[["source_id", "series_code", "geo_id", "time_period", "year", "dimensions"]].astype(str).agg("|".join,
                                                                                                         axis=1)
    df.insert(0, "obs_id", key.map(lambda k: hashlib.sha1(k.encode()).hexdigest()[:16]))
    # headline: the single value column, or a column named Total
    df["headline"] = False
    for _, g in df.groupby("series_code"):
        cats = g["dimensions"].map(lambda d: json.loads(d).get("Category"))
        if cats.isna().all():
            df.loc[g.index, "headline"] = True
        elif (cats == "Total").any():
            df.loc[g.index[cats == "Total"], "headline"] = True
    return df


def verify(rows: list[dict], pdf: Path, tol: float = 7) -> tuple[int, list[tuple]]:
    """Independent check of the text-layout parse using pdfplumber word positions.

    For every parsed table row, the period and its values must appear on the printed page (or
    the next two pages, for tables that continue), left to right, within ``tol`` points
    vertically. Returns (rows checked, rows not confirmed).
    """
    import collections

    import pdfplumber

    def norm(t: str) -> str:
        return re.sub(r"\s+", "", t)

    recs: dict = collections.OrderedDict()
    for r in rows:
        recs.setdefault((r["code"], r["page"], r["period"]), []).append(r["value_raw"])
    words, fails = {}, []
    with pdfplumber.open(pdf) as doc:
        for (code, page, period), vals in recs.items():
            first, found = period.split()[0], False
            target = norm(period[len(first):]) + "".join(norm(v) for v in vals)
            for p in (page, page + 1, page + 2):
                if p > len(doc.pages):
                    continue
                if p not in words:
                    words[p] = doc.pages[p - 1].extract_words(x_tolerance=1.5)
                for w in (w for w in words[p] if w["text"] == first):
                    near = sorted((v for v in words[p] if v["x0"] > w["x0"] and abs(v["top"] - w["top"]) <= tol),
                                  key=lambda v: v["x0"])
                    if norm(" ".join(v["text"] for v in near)).startswith(target):
                        found = True
                        break
                if found:
                    break
            if not found:
                fails.append((code, page, period, vals))
    return len(recs), fails


# Rows confirmed by looking at the rendered page because pdfplumber does not return the word
# as text (checked by eye; see docs/METHODS.md). Key: (indicator code, period, published value).
CONFIRMED_VISUALLY = {("1.3.2", "2023-24", ("54.82",)), ("5.6.1", "2015-16", ("12.9",)),
                      ("16.2.2", "2021", ("0.50",)), ("5.1.1", "From 2017 to 2023", ("83.33", "88.89", "100", "100"))}

# Tables read from the printed gridlines (second parser). Each was compared with the rendered
# page: the column labels below are copied from the page in left-to-right order, and "group" names
# a grouping column (e.g. quarter) carried down merged cells. A gridline table that is not listed
# here is never used.
GRID_REVIEW = {
    "2.2.2": {"labels": ["Wasting (%)", "Overweight (%)"]},
    "2.2.3": {"labels": ["Pregnant", "Non-Pregnant", "Total"]},
    "2.2.4": {"labels": ["Value"]},
    "3.3.5": {"labels": ["Value"]},
    "3.4.1": {"labels": ["Age 25-34", "Age 35-44", "Age 45-54", "Age 55-64", "Age 65-69"]},
    "3.6.1": {"labels": ["Death rate", "Injury rate"]},
    "4.4.1": {"labels": ["Value"]},
    "4.5.1": {"labels": ["Primary", "Secondary", "Higher Secondary", "Tertiary Education"]},
    "5.1.1": {"labels": ["Overarching legal frameworks and public life", "Violence against women",
                         "Employment and economic benefits", "Marriage and family"]},
    "5.6.1": {"labels": ["Value"]},
    "5.a.3": {"labels": ["Male", "Female"], "group": "Quarter"},
    "5.a.4": {"labels": ["Male", "Female"], "group": "Quarter"},
    "8.8.1": {"labels": ["Value"]},
    "8.9.1": {"labels": ["Total share in GDP (in %)", "Growth Rate"]},
    "9.2.1": {"labels": ["MVA as proportion of GDP, at constant price", "MVA as proportion of GDP, at current price",
                         "MVA per capita (Rs. crore/million person)"]},
    "9.c.1": {"labels": ["Population covered by a mobile-cellular network (%)",
                         "Population covered by at least a 3G mobile network (%)",
                         "Population covered by at least a 4G mobile network (%)"]},
    "10.2.2": {"labels": ["Lok Sabha", "State Assemblies", "ULB", "PRI"]},
    "10.6.1": {"labels": ["Membership (out of 11 international organizations)",
                          "Voting rights (out of 11 international organizations)"], "no_group": True},
    "11.2.1": {"labels": ["Public transport facility within 500 m from place of living (in Percentage)"]},
    "15.2.1": {"labels": ["Net change in area under forest and tree cover (sq.km.)",
                          "Above-ground biomass in forest ('000 tonnes)",
                          "Proportion of geographical area under legally established protected areas (in %)",
                          "Proportion of forest and protected area under a long-term management plan"]},
    "16.2.2": {"labels": ["Value"]},
    "16.7.1": {"labels": ["Lok Sabha", "State Assemblies", "ULB", "PRI"]},
    "17.19.2": {"labels": ["Birth registration", "Death registration"]},
}


def pdf_dates(pdf: Path) -> dict:
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        meta = doc.metadata or {}

    def iso(d: str) -> str:
        m = re.match(r"D:(\d{4})(\d{2})(\d{2})", d or "")
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
    return {"pdf_created": iso(meta.get("CreationDate", "")), "pdf_modified": iso(meta.get("ModDate", ""))}


def load_extract(reason: str) -> dict:
    """Fall back to the verified extract saved from the last successful parse of the PDF."""
    if not EXTRACT.exists():
        return {SOURCE_ID: {"status": {"status": "not available", "detail": reason}, "data": None, "skipped": []}}
    from ..io import read_observations
    df = read_observations(EXTRACT)
    skipped = pd.read_csv(EXTRACT_SKIPPED).to_dict("records") if EXTRACT_SKIPPED.exists() else []
    status = json.loads(EXTRACT_STATUS.read_text()) if EXTRACT_STATUS.exists() else {}
    status.update({"status": "loaded from verified extract", "detail": f"{reason}; using {EXTRACT.name}, parsed "
                   "and verified from the PDF whose SHA-256 is in raw_sha256"})
    return {SOURCE_ID: {"status": status, "data": df, "skipped": skipped}}


def load_all() -> dict:
    if not PDF.exists():
        return load_extract("report PDF not downloaded")
    problem = pdf_problem(PDF)
    if problem:
        return load_extract(problem)
    if not shutil.which("pdftotext"):
        return load_extract("pdftotext (Poppler) is not installed, so the PDF is not re-parsed; install it with "
                            "`brew install poppler` to rebuild from the PDF")
    pages = page_texts(PDF)
    rows, skipped = parse_snapshot(pages, snapshot_pages(pages))
    checked, fails = verify(rows, PDF)
    unresolved = [f for f in fails if (f[0], f[2], tuple(f[3])) not in CONFIRMED_VISUALLY]
    if unresolved:
        # never publish a value that the independent check cannot find on the page
        bad = {(c, per) for c, _, per, _ in unresolved}
        rows = [r for r in rows if (r["code"], r["period"]) not in bad]
    grid_rows, grid_status = grid_supplement(pages, skipped)
    if grid_rows:
        done = {r["code"] for r in grid_rows}
        rows = rows + grid_rows
        skipped = [s for s in skipped if s["code"] not in done]
    df = to_observations(rows, PDF)
    parsed_codes = sorted(set(df["indicator_code"])) if not df.empty else []
    status = {"status": "loaded", **pdf_dates(PDF),
              "indicators_in_snapshot": len(parsed_codes) + len(skipped),
              "indicators_parsed": len(parsed_codes), "indicators_not_parsed": len(skipped),
              "rows": int(len(df)), "table_rows_checked": checked,
              "confirmed_by_word_positions": checked - len(fails),
              "confirmed_visually": len(fails) - len(unresolved), "dropped_unconfirmed": len(unresolved),
              "gridline_parser": grid_status}
    if not df.empty:
        EXTRACT.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(EXTRACT, index=False)
        pd.DataFrame(skipped).to_csv(EXTRACT_SKIPPED, index=False)
        EXTRACT_STATUS.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return {SOURCE_ID: {"status": status, "data": df, "skipped": skipped}}


# ---------------------------------------------------------------- second parser: printed gridlines
GRID = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}


def _grid(table) -> list[list[dict | None]]:
    """Cell matrix with merged cells resolved: every position gets the cell that covers it.

    pdfplumber returns None for a position covered by a merged cell and '' for a cell that is
    really empty. Positions covered by a merged cell inherit its text and are marked
    ``merged=True``; genuinely empty cells stay empty.
    """
    cells = []
    for r in table.rows:
        for c in r.cells:
            if c is not None:
                cells.append(c)
    text = {c: (table.page.within_bbox(c).extract_text() or "").strip() for c in cells}
    out = []
    for r in table.rows:
        row = []
        for c in r.cells:
            if c is not None:
                row.append({"text": text[c], "bbox": c, "merged": False})
            else:
                row.append(None)
        out.append(row)
    # resolve None positions to the covering cell, using the column and row edges
    xs = [sorted({c[0] for c in cells} | {c[2] for c in cells})]
    for i, r in enumerate(table.rows):
        for j, c in enumerate(r.cells):
            if c is not None:
                continue
            col = next((rr.cells[j] for rr in table.rows if rr.cells[j] is not None), None)
            if col is None:
                continue
            x, y = (col[0] + col[2]) / 2, (r.bbox[1] + r.bbox[3]) / 2
            cover = next((cc for cc in cells if cc[0] <= x <= cc[2] and cc[1] <= y <= cc[3]), None)
            if cover is not None:
                out[i][j] = {"text": text[cover], "bbox": cover, "merged": True}
    del xs
    return out


def parse_grid(pdf: Path, page_range: range, codes: set[str]) -> tuple[list[dict], list[dict]]:
    """Read the tables of the given indicators from the printed gridlines.

    Rules: the first value-area column whose cells all hold a period is the period column;
    columns to its left are grouping labels (merged cells may carry a label down, empty cells
    may not); columns to its right are value columns, labelled by their header cells from top
    to bottom. A cell holding several lines of numbers, an empty value cell, or a missing label
    makes the whole table unreadable, and it is listed rather than guessed.
    """
    import pdfplumber

    rows_out, skipped, seen = [], [], set()
    with pdfplumber.open(pdf) as doc:
        for pidx in page_range:
            page = doc.pages[pidx]
            for table in page.find_tables(GRID):
                g = _grid(table)
                starts = [i for i, r in enumerate(g) if len(r) > 1 and r[1] and not r[1]["merged"]
                          and BLOCK.match("1 " + r[1]["text"].split("\n")[0])]
                for k, i0 in enumerate(starts):
                    m = BLOCK.match("1 " + g[i0][1]["text"].split("\n")[0])
                    code = m.group(2)
                    if code not in codes or code in seen:
                        continue
                    seen.add(code)
                    block = g[i0:starts[k + 1] if k + 1 < len(starts) else len(g)]
                    res = _read_block(block, code, pidx + 1)
                    if isinstance(res, str):
                        skipped.append({"code": code, "page": pidx + 1, "reason": res})
                    else:
                        rows_out += res
    return rows_out, skipped


def _clean_text(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("\n", " ")).strip()


def _read_block(block: list[list[dict | None]], code: str, page: int):
    width = max(len(r) for r in block)
    def cell(r, j):
        return block[r][j] if j < len(block[r]) else None
    # data rows: rows where some value-area cell is an unmerged period
    period_cols = {}
    for i, _ in enumerate(block):
        for j in range(2, width):
            c = cell(i, j)
            if c and not c["merged"] and PERIOD.match(_clean_text(c["text"])):
                period_cols.setdefault(i, j)
                break
    if not period_cols:
        return "no period column found in the gridlines"
    pcol = set(period_cols.values())
    if len(pcol) != 1:
        return "periods are in different columns in different rows"
    pcol = pcol.pop()
    data_idx = sorted(period_cols)
    first = data_idx[0]
    # every row after the first data row must be a data row (no interleaved text rows)
    tail = [i for i in range(first, len(block)) if any(cell(i, j) and cell(i, j)["text"] for j in range(2, width))]
    if tail != data_idx:
        return "text rows interleaved with data rows"
    # value columns: right of the period column, with at least one unmerged data cell
    vcols = [j for j in range(pcol + 1, width) if any(cell(i, j) and not cell(i, j)["merged"] for i in data_idx)]
    if not vcols:
        return "no value columns"
    labels = []
    for j in vcols:
        parts = []
        for i in range(0, first):
            c = cell(i, j)
            if c and c["text"] and _clean_text(c["text"]) not in parts and _clean_text(c["text"]) != code:
                if i == 0 and j == 1:
                    continue
                parts.append(_clean_text(c["text"]))
        label = " – ".join(p for p in parts if p not in ("Year", "Value"))
        labels.append(label or "Value")
    if len(set(labels)) != len(labels):
        return "value columns cannot be told apart from their headers"
    gcols = [j for j in range(2, pcol) if any(cell(i, j) and cell(i, j)["text"] for i in data_idx)]
    out = []
    for i in data_idx:
        period = _clean_text(cell(i, pcol)["text"])
        group = []
        for j in gcols:
            c = cell(i, j)
            if not c or not c["text"]:
                return "a grouping label is missing for some rows"
            group.append(_clean_text(c["text"]))
        for j, label in zip(vcols, labels, strict=True):
            c = cell(i, j)
            if c is None or c["merged"]:
                return "a value cell is merged across rows"
            raw = c["text"].strip()
            if not raw:
                return "an empty value cell (no value or marker printed)"
            if "\n" in raw:
                return "a cell holds several lines of values"
            out.append({"code": code, "page": page, "period": period, "year": start_year(period),
                        "group": " · ".join(group), "column": label, "value_raw": raw, "bbox": c["bbox"]})
    keys = [(r["group"], r["period"], r["column"]) for r in out]
    if len(set(keys)) != len(keys):
        return "rows repeat with the same group, period and column"
    return out


def _norm_label(t: str) -> str:
    t = re.sub(r"\s*[-–]\s*", "–", _clean_text(t))
    parts = []
    for x in t.split(" · "):
        if x not in parts:
            parts.append(x)
    return " · ".join(parts)


def verify_layout(rows: list[dict], pages: list[str]) -> list[tuple]:
    """Check gridline-parsed rows against Poppler's text layout (the other engine): the period and the
    row's values must appear in order on one line of the page or the next page."""
    recs: dict = {}
    for r in rows:
        recs.setdefault((r["code"], r["page"], r["group"], r["period"]), []).append(r["value_raw"])
    fails = []
    for (code, page, group, period), vals in recs.items():
        pat = (re.escape(period).replace(r"\ ", r"\s+") + r"\s+"
               + r"\s+".join(re.escape(v).replace(r"\ ", r"\s+") for v in vals) + r"(\s|$)")
        lines = [ln for p in (page, page + 1) if p <= len(pages) for ln in pages[p - 1].splitlines()]
        if not any(re.search(pat, ln) for ln in lines):
            fails.append((code, page, period, vals, group))
    return fails


def grid_supplement(pages: list[str], skipped: list[dict]) -> tuple[list[dict], dict]:
    """Read reviewed tables that the text parser skipped from the printed gridlines, keeping only
    values confirmed by the text layout (or by eye) and labels taken from GRID_REVIEW."""
    todo = {s["code"] for s in skipped} & set(GRID_REVIEW)
    if not todo:
        return [], {"tables_reviewed": len(GRID_REVIEW), "tables_used": 0}
    grid, grid_skipped = parse_grid(PDF, snapshot_pages(pages), todo)
    meta = {s["code"]: s for s in skipped}
    by_code: dict = {}
    for r in grid:
        by_code.setdefault(r["code"], []).append(r)
    fails = verify_layout(grid, pages)
    unconfirmed = {(f[0], f[2], f[4]) for f in fails
                   if (f[0], f[2], tuple(f[3])) not in CONFIRMED_VISUALLY}
    out, used, rejected = [], [], {}
    for code, rr in by_code.items():
        review = GRID_REVIEW[code]
        cols = list(dict.fromkeys(r["column"] for r in rr))
        if len(cols) != len(review["labels"]):
            rejected[code] = f"{len(cols)} value columns found, review lists {len(review['labels'])}"
            continue
        label_of = dict(zip(cols, review["labels"], strict=True))
        m = meta[code]
        for r in rr:
            if (code, r["period"], r["group"]) in unconfirmed:
                continue
            v, status, marker = clean_number(r["value_raw"])
            if status == "numeric" and re.search(r"\d\s+\d", r["value_raw"]):
                v, status = None, "text"          # e.g. '4 32': ambiguous split digits are kept as text
            group = "" if review.get("no_group") else _norm_label(r["group"])
            out.append({"code": code, "goal": m["goal"], "target": m["target"], "name": m["name"],
                        "source": m["source"], "periodicity": m["periodicity"], "page": r["page"],
                        "period": r["period"], "year": start_year(r["period"]), "column": label_of[r["column"]],
                        "group_name": review.get("group", ""), "group": group,
                        "value": v, "value_raw": r["value_raw"], "value_status": status,
                        "unit": "", "footnote": "", "parser": "gridlines (reviewed)"})
        used.append(code)
    status = {"tables_reviewed": len(GRID_REVIEW), "tables_used": len(used), "values_used": len(out),
              "rows_not_confirmed_dropped": len(unconfirmed), "rejected": rejected,
              "not_readable": {s["code"]: s["reason"] for s in grid_skipped}}
    return out, status
