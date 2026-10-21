"""NITI Aayog, National Multidimensional Poverty Index: A Progress Review 2023 (district tables).

For every State and UT the report prints an "Overview of Districts" table with, for NFHS-4 (2015-16)
and NFHS-5 (2019-21): the headcount ratio H (% of people who are multidimensionally poor), the
intensity A (average share of deprivations among the poor) and the MPI (= H x A).

The PDF contains hidden text: some pages carry an earlier copy of a neighbouring State's table
underneath the visible one (for example Assam's districts under Bihar's). It is covered by white
row rectangles drawn later, so it is invisible on the printed page but still in the text layer.
Characters that a later-drawn filled shape covers are therefore dropped before parsing.

Each row is accepted only if it passes an independent arithmetic check: the published MPI must
equal H x A within rounding (|H*A - MPI| <= 0.0015). Rows that fail, or that cannot be read
without guessing, are listed in ``not_parsed`` with the page number instead of being loaded.
These figures are survey-based estimates from NFHS and are kept apart from the NFHS indicators.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .. import config
from ..http import sha256

SOURCE_ID = "NITI_MPI_2023"
URL = "https://www.niti.gov.in/sites/default/files/2023-08/India-National-Multidimentional-Poverty-Index-2023.pdf"
PDF = config.RAW / "niti_mpi" / "India-National-Multidimentional-Poverty-Index-2023.pdf"
EXTRACT = config.REFERENCE / "niti_mpi_2023_districts.csv"
NUM = re.compile(r"^(\d{1,3}\.\d{1,2})%$|^(0\.\d{3})$|^[–-]$")
COLS = ("hcr4", "int4", "mpi4", "hcr5", "int5", "mpi5")


def _visible_chars(page) -> list[dict]:
    """pdfplumber chars that no later-drawn filled shape covers (hidden layers removed)."""
    from pdfminer.layout import LTChar, LTCurve, LTFigure, LTRect

    objs: list = []

    def walk(container):
        for o in container:
            if isinstance(o, LTFigure):
                walk(o)
            else:
                objs.append(o)

    walk(page.layout._objs)
    fills = [(i, o) for i, o in enumerate(objs) if isinstance(o, (LTRect, LTCurve)) and getattr(o, "fill", False)]
    hidden = set()
    for i, o in enumerate(objs):
        if not isinstance(o, LTChar):
            continue
        later = [f for j, f in fills if j > i and f.x0 < o.x1 and f.x1 > o.x0 and f.y0 < o.y1 and f.y1 > o.y0]
        if not later:
            continue
        # hidden when every sample point of the glyph box lies under some later-drawn fill
        # (a glyph can straddle two row rectangles)
        w, ht = o.x1 - o.x0, o.y1 - o.y0
        pts = [(o.x0 + w * fx, o.y0 + ht * fy) for fx in (0.2, 0.5, 0.8) for fy in (0.25, 0.5, 0.75)]
        if all(any(f.x0 <= x <= f.x1 and f.y0 <= y <= f.y1 for f in later) for x, y in pts):
            hidden.add((round(o.x0, 2), round(o.y0, 2), o.get_text()))
    h = page.height
    return [c for c in page.chars if (round(c["x0"], 2), round(h - c["bottom"], 2), c["text"]) not in hidden]


def _words(page):
    import pdfplumber  # noqa: F401  (imported for the page type)

    keep = {(round(c["x0"], 2), round(c["top"], 2), c["text"]) for c in _visible_chars(page)}
    vis = page.filter(lambda o: o.get("object_type") != "char"
                      or (round(o["x0"], 2), round(o["top"], 2), o["text"]) in keep)
    return vis.extract_words(keep_blank_chars=False, x_tolerance=1.5, y_tolerance=2)


def _value(s: str):
    if s in ("–", "-"):
        return None
    return float(s.rstrip("%"))


def parse_page(page, page_no: int) -> tuple[str, list[dict], list[dict]]:
    words = _words(page)
    text = " ".join(w["text"] for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])))
    m = re.search(r"([A-Z][a-z][A-Za-z&.\- ]*?):\s*Overview of Districts?", text)
    state = m.group(1).strip() if m else ""
    problems: list[dict] = []
    # the table header: an "NFHS-4" label with "NFHS-5" to its right on the same line (last such pair on the page)
    pairs = [(w4, w5) for w4 in words if w4["text"] == "NFHS-4" for w5 in words
             if w5["text"] == "NFHS-5" and abs(w5["top"] - w4["top"]) < 3 and w5["x0"] > w4["x0"] + 100]
    if not pairs:
        return state, [], [{"page": page_no, "state": state, "district": "", "reason": "table header not found"}]
    w4, w5 = max(pairs, key=lambda p: p[0]["top"])
    sub = [w for w in words if w["text"] in ("Headcount", "Ratio", "Intensity", "MPI", "District")
           and w4["top"] < w["top"] < w4["top"] + 30]
    top = (max(w["bottom"] for w in sub) if sub else w4["bottom"] + 10) + 0.5  # below the header lines
    body = [w for w in words if w["top"] > top and w["bottom"] < page.height - 40]
    vals = [w for w in body if w["x0"] > w4["x0"] - 80 and NUM.match(w["text"])]
    # six value columns, found from the numbers themselves (1-D clusters of cell centres)
    mids = sorted((v["x0"] + v["x1"]) / 2 for v in vals)
    clusters: list[list[float]] = []
    for m_ in mids:
        if clusters and m_ - clusters[-1][-1] < 14:
            clusters[-1].append(m_)
        else:
            clusters.append([m_])
    clusters = [c for c in clusters if len(c) >= 1]
    if len(clusters) != 6:
        return state, [], [{"page": page_no, "state": state, "district": "",
                            "reason": f"expected 6 value columns, found {len(clusters)}"}]
    centres = dict(zip(COLS, (sum(c) / len(c) for c in clusters), strict=True))
    first_val_x = min(v["x0"] for v in vals) - 4
    skip = {"District", "Headcount", "Ratio", "Intensity", "MPI"}
    names = [w for w in body if w["x1"] < first_val_x and w["text"] not in skip and not re.fullmatch(r"\d+", w["text"])]
    # rows = distinct vertical positions of numeric cells
    ys: list[float] = []
    for v in sorted(vals, key=lambda w: w["top"]):
        if not ys or v["top"] - ys[-1] > 3:
            ys.append(v["top"])
    gap = min((b - a for a, b in zip(ys, ys[1:], strict=False)), default=20)

    def col_of(w):
        mid = (w["x0"] + w["x1"]) / 2
        return min(centres, key=lambda k: abs(mid - centres[k]))

    # each name word belongs to the row whose numbers sit closest to it vertically (names may wrap)
    by_row: dict[float, list] = {}
    for n in names:
        mid = (n["top"] + n["bottom"]) / 2
        y = min(ys, key=lambda yy: abs(mid - (yy + 4)), default=None)
        if y is not None and abs(mid - (y + 4)) < max(gap * 0.75, 9):
            by_row.setdefault(y, []).append(n)
    rows = []
    for y in ys:
        cells = {k: [] for k in COLS}
        for v in vals:
            if abs(v["top"] - y) <= 3:
                cells[col_of(v)].append(v["text"])
        nm = sorted(by_row.get(y, []), key=lambda n: (round(n["top"]), n["x0"]))
        name = re.sub(r"\s+", " ", " ".join(n["text"] for n in nm)).strip()
        row = {"page": page_no, "state": state, "district": name}
        ok = bool(name)
        for k in COLS:
            c = cells[k]
            row[k] = c[0] if len(c) == 1 else ""
            if len(c) > 1:
                ok = False
        rows.append((row, ok))
    out = []
    for row, ok in rows:
        reason = "" if ok else "row could not be read unambiguously"
        if not row["district"] and not any(row[k] for k in ("hcr5", "int5", "mpi5")):
            reason = "stray dashes with no district name and no NFHS-5 values (remnant of the hidden text layer)"
        if ok:
            for rnd in ("4", "5"):
                h, a, m = (row[f"{k}{rnd}"] for k in ("hcr", "int", "mpi"))
                if not h or h in ("–", "-"):
                    continue  # district not covered in that round (formed later)
                hv, av, mv = _value(h), _value(a) if a else None, _value(m) if m else None
                if hv == 0 and (mv in (None, 0.0)):
                    continue
                if av is None or mv is None or abs(hv / 100 * av / 100 - mv) > 0.0015:
                    reason = f"MPI does not equal H x A for NFHS-{rnd}"
        if reason:
            problems.append({**row, "reason": reason})
        else:
            out.append(row)
    return state, out, problems


def extract(pdf_path: Path = PDF) -> tuple[pd.DataFrame, pd.DataFrame]:
    import pdfplumber

    rows, problems = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            t = page.extract_text() or ""
            if "Overview of District" not in t:
                continue
            _, r, p = parse_page(page, i)
            rows += r
            problems += p
    df = pd.DataFrame(rows, columns=["page", "state", "district", *COLS])
    pr = pd.DataFrame(problems)
    df.insert(0, "raw_sha256", sha256(pdf_path))
    return df, pr


# ---------------------------------------------------------------- fetch, load and match to NFHS districts
ALIASES = config.REFERENCE / "niti_mpi_district_aliases.csv"


def fetch(refresh: bool = False) -> Path:
    from ..http import DownloadError, download, pdf_problem, session

    path = download(URL, PDF, refresh=refresh or bool(pdf_problem(PDF)), sess=session(), timeout=600,
                    min_bytes=1_000_000)
    problem = pdf_problem(path)
    if problem:
        raise DownloadError(f"{path.name}: {problem}")
    return path


def district_key(name: str) -> str:
    """Lower-case letters only; '&' read as 'and'. Used to compare district names across sources."""
    import unicodedata

    s = unicodedata.normalize("NFKD", str(name).lower()).replace("&", "and")
    return re.sub(r"[^a-z]", "", s)


def match_districts(rows: pd.DataFrame, districts: pd.DataFrame, state_col: str = "state",
                    name_col: str = "district") -> pd.Series:
    """geo_id for each row: same name within the same State, a name in brackets, or a reviewed alias.

    Anything else stays unmatched (NaN). A district split or merged since NFHS-5 is never assigned
    to a different district."""
    from .. import geography

    aliases = {}
    if ALIASES.exists():
        a = pd.read_csv(ALIASES)
        aliases = {(r.state_as_published, district_key(r.district_as_published)): r.geo_id for r in a.itertuples()}
    by_state: dict[str, dict[str, str]] = {}
    for r in districts.itertuples():
        by_state.setdefault(r.parent_geo_id, {})[district_key(r.geography)] = r.geo_id
    out = []
    for r in rows.itertuples():
        state, name = getattr(r, state_col), str(getattr(r, name_col))
        st = geography.resolve(state)
        keys = [district_key(name)]
        m = re.match(r"(.*?)\s*\((.*)\)\s*$", name)
        if m:
            keys += [district_key(m.group(1)), district_key(m.group(2))]
        hit = next((by_state.get(st, {})[k] for k in keys if k in by_state.get(st, {})), None)
        out.append(hit or aliases.get((state, district_key(name))))
    return pd.Series(out, index=rows.index, dtype="object")


def load(districts: pd.DataFrame) -> dict:
    """District MPI rows matched to the NFHS district list.

    Uses the verified extract in data/reference; if the report PDF is present and differs from the
    file the extract was made from, the extract is rebuilt from the PDF first."""
    status = {"status": "not available"}
    if PDF.exists():
        current = sha256(PDF)
        old = pd.read_csv(EXTRACT, dtype=str) if EXTRACT.exists() else pd.DataFrame()
        if old.empty or old["raw_sha256"].iloc[0] != current:
            df, pr = extract(PDF)
            df.to_csv(EXTRACT, index=False)
            pr.to_csv(EXTRACT.with_name(EXTRACT.stem + "_not_parsed.csv"), index=False)
    if not EXTRACT.exists():
        return {"data": pd.DataFrame(), "skipped": [], "status": {**status, "detail": f"{EXTRACT.name} missing"}}
    df = pd.read_csv(EXTRACT, dtype=str, keep_default_na=False)
    np_file = EXTRACT.with_name(EXTRACT.stem + "_not_parsed.csv")
    skipped = pd.read_csv(np_file, dtype=str, keep_default_na=False).to_dict("records") if np_file.exists() else []
    df["geo_id"] = match_districts(df, districts) if len(districts) else None
    matched = df[df["geo_id"].notna()]
    dup = matched[matched["geo_id"].duplicated(keep=False)]
    if len(dup):
        raise ValueError(f"MPI: several rows matched to one district: {dup[['state', 'district', 'geo_id']].values}")
    unmatched = df[df["geo_id"].isna()]
    skipped += [{"page": r.page, "state": r.state, "district": r.district,
                 "reason": "no matching NFHS-5 district (new, split, renamed or not in the NFHS fact sheets)"}
                for r in unmatched.itertuples()]
    return {"data": df, "skipped": skipped,
            "status": {"status": "loaded", "rows_in_report": int(len(df)), "matched_districts": int(len(matched)),
                       "unmatched_rows": int(len(unmatched)), "rows_not_read": int(len(skipped) - len(unmatched)),
                       "checked": "every loaded row satisfies MPI = H x A within rounding",
                       "pdf_available": PDF.exists()}}
