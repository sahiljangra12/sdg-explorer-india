"""UN Global SDG Indicators Database: India's observations and the indicator/series metadata.

Data come from the UNSD SDG API v1 (``/Indicator/Data?areaCode=356``), page by page. The
download is checked for completeness: every page from 1 to ``totalPages`` must be present
and the number of records must equal ``totalElements``. Otherwise the build stops rather
than silently publishing a partial dataset.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pandas as pd

from .. import config
from ..http import DownloadError, download, read_meta, session, sha256, write_meta

SOURCE_ID = "UN_SDG_API"
RAW_DIR = config.RAW / "un_sdg"
DATA_URL = f"{config.UN_API_BASE}/Indicator/Data"
GOAL_LIST_URL = f"{config.UN_API_BASE}/Goal/List"
SERIES_LIST_URL = f"{config.UN_API_BASE}/Series/List"

# Codes the UN database uses for "all categories" of a dimension
TOTAL_CODES = {"BOTHSEX", "ALLAREA", "ALLAGE", "_T", "ALL", "TOTAL", "_Z", "ALLSIZE", "ALLINCOME",
               "ALLWEALTH", "ALLEDU", "ALLDISABILITY", "ALLHOUSEHOLDS", "ALLDOMAINS", "DRUG_TOTAL"}
# "Reporting Type" (G = global database, N = nationally reported) is published as a dimension but is
# not a population breakdown: it is moved to its own column and excluded from headline selection.
REPORTING = "Reporting Type"


class IncompleteDownload(RuntimeError):
    pass


def page_path(n: int, folder: Path | None = None) -> Path:
    return (folder or RAW_DIR) / f"india_page_{n:04d}.json"


# ---------------------------------------------------------------- download
def fetch(refresh: bool = False, page_size: int = config.UN_PAGE_SIZE) -> list[Path]:
    """Download every page of India's UN SDG data plus the metadata lists.

    Without ``refresh``, a complete cached download is reused. With ``refresh``, pages are
    downloaded into a staging folder, checked for completeness, and only then swapped in, so
    a failed refresh never leaves a mix of old and new pages.
    """
    if not refresh:
        try:
            load_pages()
            return sorted(RAW_DIR.glob("india_page_[0-9][0-9][0-9][0-9].json"))
        except (FileNotFoundError, IncompleteDownload):
            pass
    stage = RAW_DIR.parent / (RAW_DIR.name + ".staging")
    shutil.rmtree(stage, ignore_errors=True)
    sess = session()
    params = {"areaCode": config.INDIA_M49, "pageSize": page_size}
    first = download(DATA_URL, page_path(1, stage), params={**params, "page": 1}, sess=sess, min_bytes=50)
    total_pages = int(json.loads(first.read_text(encoding="utf-8")).get("totalPages") or 1)
    for n in range(2, total_pages + 1):
        download(DATA_URL, page_path(n, stage), params={**params, "page": n}, sess=sess, min_bytes=50)
        print(f"  UN SDG API page {n}/{total_pages}")
    download(GOAL_LIST_URL, stage / "goal_list.json", params={"includechildren": "true"}, sess=sess)
    download(SERIES_LIST_URL, stage / "series_list.json", params={"allreleases": "false"}, sess=sess)
    load_pages(stage)                         # raises if incomplete; the old data stay in place
    backup = RAW_DIR.parent / (RAW_DIR.name + ".previous")
    shutil.rmtree(backup, ignore_errors=True)
    if RAW_DIR.exists():
        RAW_DIR.rename(backup)
    stage.rename(RAW_DIR)
    shutil.rmtree(backup, ignore_errors=True)
    return sorted(RAW_DIR.glob("india_page_[0-9][0-9][0-9][0-9].json"))


def import_files(src: Path) -> list[Path]:
    """Import UN API responses downloaded elsewhere (e.g. with curl) into the raw folder.

    Pages are identified by the ``pageNumber`` inside each file, not by file name. The
    original file name and SHA-256 are recorded in the provenance record.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    imported = []
    for f in sorted(Path(src).glob("*.json")):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise DownloadError(f"{f.name} is not valid JSON: {e}") from e
        if isinstance(obj, dict) and "pageNumber" in obj and "data" in obj:
            n = int(obj["pageNumber"])
            if not obj["data"] and n > int(obj.get("totalPages") or 0):
                continue                          # an empty page past the end
            dest = page_path(n)
            url = f"{DATA_URL}?areaCode={config.INDIA_M49}&pageSize={obj.get('size')}&page={n}"
        elif isinstance(obj, list) and obj and "targets" in obj[0]:
            dest, url = RAW_DIR / "goal_list.json", f"{GOAL_LIST_URL}?includechildren=true"
        elif isinstance(obj, list) and obj and "release" in obj[0] and "code" in obj[0]:
            dest, url = RAW_DIR / "series_list.json", f"{SERIES_LIST_URL}?allreleases=false"
        else:
            continue
        shutil.copyfile(f, dest)
        write_meta(dest, url, 200, note=f"Downloaded outside the pipeline and imported from '{f.name}' "
                                        f"(sha256 {sha256(f)}).")
        imported.append(dest)
    return imported


# ---------------------------------------------------------------- load and check
def load_pages(raw_dir: Path = RAW_DIR) -> list[tuple[dict, Path]]:
    files = sorted(raw_dir.glob("india_page_[0-9][0-9][0-9][0-9].json"))
    if not files:
        raise FileNotFoundError(f"No UN SDG pages in {raw_dir}. Run `python -m sdg_india fetch`.")
    pages = {}
    for f in files:
        obj = json.loads(f.read_text(encoding="utf-8"))
        pages[int(obj["pageNumber"])] = (obj, f)
    first = pages[min(pages)][0]
    total_pages, total = int(first["totalPages"]), int(first["totalElements"])
    missing = sorted(set(range(1, total_pages + 1)) - set(pages))
    if missing:
        raise IncompleteDownload(f"UN SDG pages missing: {missing[:20]} (of {total_pages}).")
    if any(int(p[0]["totalElements"]) != total for p in pages.values()):
        raise IncompleteDownload("Pages come from different snapshots (totalElements differs); download again.")
    got = sum(len(pages[n][0].get("data") or []) for n in range(1, total_pages + 1))
    if got != total:
        raise IncompleteDownload(f"UN SDG records: got {got}, API reported {total}.")
    return [pages[n] for n in range(1, total_pages + 1)]


# ---------------------------------------------------------------- parse
def parse_value(raw) -> float | None:
    """Strict numeric parse: values such as '<0.1', '>95' or 'N' are not numbers and stay missing."""
    if raw is None:
        return None
    s = str(raw).strip()
    if re.fullmatch(r"[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?", s):
        return float(s)
    return None


NOT_AVAILABLE = {"NAN", "N", "NA", "N/A", "..", "-", ""}


def value_status(raw) -> str:
    """'numeric', 'not_available' (the publisher's own missing-value marker, e.g. 'NaN = Not Available'),
    or 'text' (a published non-numeric value such as '<0.1')."""
    if parse_value(raw) is not None:
        return "numeric"
    return "not_available" if raw is None or str(raw).strip().upper() in NOT_AVAILABLE else "text"


def _goals(indicators: list[str]) -> str:
    return ";".join(str(g) for g in sorted({int(i.split(".")[0]) for i in indicators if i.split(".")[0].isdigit()}))


def _first_int(xs) -> int | None:
    for x in xs or []:
        m = re.match(r"\d+", str(x))
        if m:
            return int(m.group())
    return None


def series_releases(raw_dir: Path = RAW_DIR) -> dict[str, str]:
    f = raw_dir / "series_list.json"
    if not f.exists():
        return {}
    return {s["code"]: s.get("release", "") for s in json.loads(f.read_text(encoding="utf-8"))}


def parse_observations(pages: list[tuple[dict, Path]], releases: dict[str, str] | None = None) -> pd.DataFrame:
    releases = releases or {}
    rows = []
    for obj, path in pages:
        meta = read_meta(path)
        url, retrieved, digest = meta.get("url", ""), meta.get("retrieved_at", ""), meta.get("sha256") or sha256(path)
        for x in obj.get("data") or []:
            attrs = x.get("attributes") or {}
            dims = {k: v for k, v in sorted((x.get("dimensions") or {}).items()) if v not in (None, "")}
            reporting = dims.pop(REPORTING, None) or attrs.get(REPORTING, "")
            year = x.get("timePeriodStart")
            series = str(x.get("series") or "")
            indicators = [str(i) for i in (x.get("indicator") or [])]
            time_detail = x.get("time_detail") or x.get("timeCoverage") or ""
            raw_value = x.get("value")
            rows.append({
                "source_id": SOURCE_ID,
                "goal": _first_int(x.get("goal")),
                "target": ";".join(map(str, x.get("target") or [])),
                "indicator_code": indicators[0] if indicators else "",
                "indicator_codes_all": ";".join(indicators),
                "goals_all": _goals(indicators),
                "series_code": series,
                "series_description": x.get("seriesDescription") or "",
                "geo_id": "IN" if str(x.get("geoAreaCode")) == str(config.INDIA_M49) else f"M49:{x.get('geoAreaCode')}",
                "geography": "India" if str(x.get("geoAreaCode")) == str(config.INDIA_M49)
                else x.get("geoAreaName", ""),
                "geo_level": "national",
                "year": int(float(year)) if year not in (None, "") else None,
                "time_period": str(time_detail) if time_detail else (str(int(float(year))) if year else ""),
                "value": parse_value(raw_value),
                "value_raw": "" if raw_value is None else str(raw_value),
                "value_status": value_status(raw_value),
                "unit": attrs.get("Units", ""),
                "unit_multiplier": attrs.get("UnitMultiplier", ""),
                "nature": attrs.get("Nature", ""),
                "reporting_type": reporting,
                "dimensions": json.dumps(dims, ensure_ascii=False, sort_keys=True),
                "lower_bound": parse_value(x.get("lowerBound")),
                "upper_bound": parse_value(x.get("upperBound")),
                "base_period": x.get("basePeriod") or "",
                "original_source": x.get("source") or "",
                "footnotes": " | ".join(str(f) for f in (x.get("footnotes") or []) if f),
                "release": releases.get(series, ""),
                "source_url": url,
                "raw_file": f"{path.parent.name}/{path.name}",
                "raw_sha256": digest,
                "retrieved_at": retrieved,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    key_cols = ["source_id", "series_code", "geo_id", "time_period", "year", "dimensions", "reporting_type"]
    key = df[key_cols].astype(str).agg("|".join, axis=1)
    df.insert(0, "obs_id", key.map(lambda k: hashlib.sha1(k.encode()).hexdigest()[:16]))
    df = collapse_repeats(df)
    df["headline"] = headline_flags(df)
    return df


PROVENANCE = ["source_url", "raw_file", "raw_sha256", "retrieved_at"]


def collapse_repeats(df: pd.DataFrame) -> pd.DataFrame:
    """Merge records the API returns more than once.

    A series linked to several SDG indicators (e.g. EN_MAT_DOMCMPG under 8.4.2 and 12.2.2) is
    returned once per indicator. Such copies are merged only if everything except provenance
    is identical; any other repeat is an error. Provenance of every copy is kept.
    """
    dup = df["obs_id"].duplicated(keep=False)
    if not dup.any():
        df.attrs["repeats_merged"] = 0
        return df
    content = [c for c in df.columns if c not in PROVENANCE]
    conflicts = df[dup].astype(str).groupby("obs_id")[content].nunique().gt(1).any(axis=1)
    if conflicts.any():
        raise IncompleteDownload(f"{int(conflicts.sum())} records repeat with different content, "
                                 f"e.g. obs_id {conflicts[conflicts].index[0]}; the download is inconsistent.")
    agg = {c: "first" for c in content if c != "obs_id"}
    agg.update({c: (lambda x: " ; ".join(dict.fromkeys(x.astype(str)))) for c in PROVENANCE})
    merged = df.groupby("obs_id", sort=False, as_index=False).agg(agg)[df.columns]
    merged.attrs["repeats_merged"] = int(len(df) - len(merged))
    return merged


def headline_flags(df: pd.DataFrame) -> pd.Series:
    """True for the 'total' row of each series (e.g. both sexes, all areas).

    For each series, only dimensions that vary are considered. A row is headline when every
    varying dimension is at a total code. If a varying dimension has no total code (e.g. a
    series published only by age group), no row is marked and users pick the breakdown.
    """
    flags = pd.Series(False, index=df.index)
    for _, g in df.groupby("series_code", sort=False):
        dims = g["dimensions"].map(json.loads)
        keys = sorted({k for d in dims for k in d})
        varying = [k for k in keys if dims.map(lambda d, k=k: d.get(k)).nunique(dropna=False) > 1]
        if not varying:
            flags[g.index] = True
            continue
        ok = dims.map(lambda d, v=tuple(varying): all(str(d.get(k, "")).upper() in TOTAL_CODES for k in v))
        flags[g.index] = ok.values
    return flags


def parse_metadata(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """One row per goal / target / indicator / series from the UN Goal List."""
    f = raw_dir / "goal_list.json"
    if not f.exists():
        return pd.DataFrame()
    current = series_releases(raw_dir)
    rows = []
    for g in json.loads(f.read_text(encoding="utf-8")):
        for t in g.get("targets") or []:
            for ind in t.get("indicators") or []:
                series = ind.get("series") or [{}]
                for s in series:
                    rows.append({
                        "goal": _first_int([g.get("code")]),
                        "goal_title": g.get("title", ""),
                        "target": t.get("code", ""),
                        "target_description": t.get("description") or t.get("title", ""),
                        "indicator_code": ind.get("code", ""),
                        "indicator_description": ind.get("description", ""),
                        "tier": ind.get("tier", ""),
                        "series_code": s.get("code", ""),
                        "series_description": s.get("description", ""),
                        "release": current.get(s.get("code", ""), s.get("release", "")),
                        "metadata_url": f"https://unstats.un.org/sdgs/metadata/?Text=&Goal={g.get('code')}"
                                        f"&Target={t.get('code')}",
                    })
    return pd.DataFrame(rows).drop_duplicates()
