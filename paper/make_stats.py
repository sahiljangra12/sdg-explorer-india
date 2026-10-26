"""Compute every number, table and figure used in the paper from the SDG Explorer India data files.

Run:  python make_stats.py <repo>    (writes stats.tex, tab_*.tex, fig_*.pdf, numbers.json next to this script)
Nothing in the paper is typed by hand: text numbers are LaTeX macros defined in stats.tex.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

REPO = Path(sys.argv[1]).resolve()
OUT = Path(__file__).resolve().parent
P = REPO / "data" / "processed"
R = REPO / "data" / "reference"
GC = [
    "",
    "#e5243b",
    "#dda63a",
    "#4c9f38",
    "#c5192d",
    "#ff3a21",
    "#26bde2",
    "#fcc30b",
    "#a21942",
    "#fd6925",
    "#dd1367",
    "#fd9d24",
    "#bf8b2e",
    "#3f7e44",
    "#0a97d9",
    "#56c02b",
    "#00689d",
    "#19486a",
]
INK = "#1b2140"
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["DejaVu Serif"],
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#555",
        "axes.labelcolor": INK,
        "xtick.color": "#333",
        "ytick.color": "#333",
        "pdf.fonttype": 42,
        "axes.titlesize": 9.5,
    }
)

M: dict[str, str] = {}  # LaTeX macros
NUM: dict[str, object] = {}  # same values, machine-readable


def tex_escape(s: str) -> str:
    return (
        str(s)
        .replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("_", r"\_")
        .replace("#", r"\#")
        .replace("$", r"\$")
        .replace("~", r"\textasciitilde{}")
        .replace("^", r"\^{}")
        .replace("–", "--")
        .replace("—", "---")
        .replace("≥", r"$\geq$")
        .replace("<", r"$<$")
        .replace(">", r"$>$")
    )


def change_cell(r) -> str:
    return f"{f(r.medch)} [{f(r.q1)}, {f(r.q3)}]" if r.npair else "no NFHS-4 values"


def n(x) -> str:
    """Integer with thousands separators for LaTeX."""
    return f"{int(x):,}".replace(",", "{,}")


def f(x, d=1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "--"
    s = f"{x:.{d}f}"
    if s.startswith("-") and float(s) == 0:
        s = s[1:]
    return s.replace("-", "\\ensuremath{-}")


def mac(name: str, value: str, raw=None) -> None:
    assert re.fullmatch(r"[A-Za-z]+", name), name
    assert name not in M, f"duplicate macro {name}"
    M[name] = value
    NUM[name] = raw if raw is not None else value


# ------------------------------------------------------------------ load
man = json.loads((P / "manifest.json").read_text())
obs = pd.read_csv(P / "observations.csv", low_memory=False)
ind = pd.read_csv(P / "indicators.csv")
scores = pd.read_csv(P / "index_scores.csv")
ctx = pd.read_csv(P / "district_context.csv")
np_ = pd.read_csv(P / "not_parsed.csv")
geos = pd.read_csv(P / "geographies.csv")
summ = json.loads((REPO / "docs" / "data" / "summary.json").read_text())
dist = json.loads((REPO / "docs" / "data" / "districts.json").read_text())
mpi_x = pd.read_csv(R / "niti_mpi_2023_districts.csv", dtype=str, keep_default_na=False)
asp_x = pd.read_csv(R / "niti_aspirational_districts.csv", dtype=str, keep_default_na=False)
meta = lambda p: json.loads((REPO / "data" / "raw" / (p + ".meta.json")).read_text())  # noqa: E731

# ------------------------------------------------------------------ totals
t = man["totals"]
mac("nRecords", n(t["records"]), t["records"])
mac("nObs", n(t["observations"]), t["observations"])
mac("nNumeric", n(t["numeric_observations"]), t["numeric_observations"])
mac("nText", n(t["text_observations"]), t["text_observations"])
mac("nNA", n(t["not_available_markers"]), t["not_available_markers"])
mac("nIndicators", n(t["indicators"]), t["indicators"])
mac("nSeries", n(t["series"]), t["series"])
mac("yFirst", str(t["earliest_year"]))
mac("yLast", str(t["latest_year"]))
mac("nBeforeFifteen", n(t["observations_before_2015"]), t["observations_before_2015"])
bs = man["by_source"]
for key, sid in (("UN", "UN_SDG_API"), ("Mospi", "MOSPI_NIF_2025"), ("Nfhs", "NFHS5_DISTRICTS")):
    s = bs[sid]
    mac(f"obs{key}", n(s["observations"]), s["observations"])
    mac(f"rec{key}", n(s["records"]), s["records"])
    mac(f"na{key}", n(s["not_available_markers"]), s["not_available_markers"])
    mac(f"ind{key}", n(s["indicators"]), s["indicators"])
    mac(f"ser{key}", n(s["series"]), s["series"])
    mac(f"first{key}", str(s["earliest_year"]))
    mac(f"last{key}", str(s["latest_year"]))
    mac(f"pre{key}", n(s["observations_before_2015"]), s["observations_before_2015"])
mac("numMospi", n(bs["MOSPI_NIF_2025"]["numeric_observations"]), bs["MOSPI_NIF_2025"]["numeric_observations"])
mac("textMospi", n(bs["MOSPI_NIF_2025"]["text_observations"]), bs["MOSPI_NIF_2025"]["text_observations"])
nat_obs = sum(bs[s]["observations"] for s in ("UN_SDG_API", "MOSPI_NIF_2025"))
mac("obsNational", n(nat_obs), nat_obs)

st = man["source_status"]
u = st["UN_SDG_API"]
mac("unPages", str(u["pages"]))
mac("unApiRecords", n(u["records_in_api"]), u["records_in_api"])
mac("unRepeats", n(u["repeats_merged"]), u["repeats_merged"])
mac("unUnique", n(u["unique_observations"]), u["unique_observations"])
mo = st["MOSPI_NIF_2025"]
for k, name in (
    ("indicators_in_snapshot", "moSnapshot"),
    ("indicators_parsed", "moParsed"),
    ("indicators_not_parsed", "moNotParsed"),
    ("rows", "moRows"),
    ("table_rows_checked", "moRowsChecked"),
    ("confirmed_by_word_positions", "moConfirmedWords"),
    ("confirmed_visually", "moConfirmedVisual"),
):
    mac(name, n(mo[k]), mo[k])
mac("moGridTables", n(mo["gridline_parser"]["tables_used"]), mo["gridline_parser"]["tables_used"])
mac("moGridValues", n(mo["gridline_parser"]["values_used"]), mo["gridline_parser"]["values_used"])
mac("moPdfCreated", mo["pdf_created"])

# provenance (retrieval dates and checksums)
prov = {
    "UN": meta("un_sdg/india_page_0001.json"),
    "Mospi": meta("mospi/SDG_NIF_Progress_Report_2025.pdf"),
    "Niti": meta("niti/SDG_India_Index_2023-24.pdf"),
    "Mpi": meta("niti_mpi/India-National-Multidimentional-Poverty-Index-2023.pdf"),
    "Asp": meta("niti_aspirational/List-of-112-Aspirational-Districts.pdf"),
    "Geo": meta("datameet_states/Admin2.shp"),
}
for k, m in prov.items():
    mac(f"date{k}", m["retrieved_at"][:10])
    mac(f"sha{k}", m["sha256"][:12])
    if k != "UN":
        mac(f"mb{k}", f"{m['bytes'] / 1e6:.1f}", m["bytes"])

# ------------------------------------------------------------------ UN coverage (unique series)
mac("unDiscontinued", str(int((~ind.drop_duplicates("series_code")["in_use"].astype(bool)).sum())))
ind = ind[ind["in_use"].astype(bool)]  # series marked "(Not In Use)" in every UN listing are not counted
un_list = ind.drop_duplicates("series_code")
num = obs[obs["value_status"] == "numeric"]
un_num_series = set(num.loc[num["source_id"] == "UN_SDG_API", "series_code"])
un_any_series = set(obs.loc[obs["source_id"] == "UN_SDG_API", "series_code"])
listed = set(un_list["series_code"])
mac("unListed", n(len(listed)), len(listed))
mac("unListedInd", n(ind["indicator_code"].nunique()), ind["indicator_code"].nunique())
mac("unWithNum", n(len(un_num_series & listed)), len(un_num_series & listed))
mac("unOnlyNA", n(len((un_any_series - un_num_series) & listed)), len((un_any_series - un_num_series) & listed))
mac("unNoRecord", n(len(listed - un_any_series)), len(listed - un_any_series))
mac("unShare", f(100 * len(un_num_series & listed) / len(listed)), 100 * len(un_num_series & listed) / len(listed))
assert len(un_num_series - listed) == 0, "a UN series with data is missing from the list"

# per goal (a series linked to several goals is counted under each)
rows = []
for g in range(1, 18):
    lg = set(ind.loc[ind["goal"] == g, "series_code"])
    gs = summ["goals"][g - 1]
    with_num = len(lg & un_num_series)
    assert with_num == gs["series_un"], (g, with_num, gs["series_un"])
    nat = obs[(obs["geo_level"] != "district")]
    ex = nat.assign(goals_all=nat["goals_all"].astype(str).str.split(r"[ ;,|]+")).explode("goals_all")
    eg = ex[(ex["goals_all"] == str(g)) & (ex["value_status"] == "numeric")].drop_duplicates("obs_id")
    rows.append(
        {
            "goal": g,
            "name": gs["name"],
            "listed": len(lg),
            "withd": with_num,
            "share": 100 * with_num / len(lg),
            "mospi": gs["series_mospi"],
            "obs": len(eg),
            "y0": int(eg["year"].min()),
            "y1": int(eg["year"].max()),
        }
    )
cov = pd.DataFrame(rows)
best, worst = cov.loc[cov["share"].idxmax()], cov.loc[cov["share"].idxmin()]
mac("bestGoal", str(int(best.goal)))
mac("bestGoalName", tex_escape(best["name"]))
mac("bestGoalShare", f(best.share, 0), best.share)
mac("worstGoal", str(int(worst.goal)))
mac("worstGoalName", tex_escape(worst["name"]))
mac("worstGoalShare", f(worst.share, 0), worst.share)
low = cov[cov["share"] < 50].sort_values("share")
mac("nGoalsBelowHalf", str(len(low)), len(low))
mac("goalsBelowHalf", ", ".join(str(int(x)) for x in sorted(low["goal"])))
with open(OUT / "tab_goals.tex", "w") as fh:
    for r in rows:
        fh.write(
            f"{r['goal']} & {tex_escape(r['name'])} & {r['listed']} & {r['withd']} & {r['share']:.0f} & {r['mospi']} & "
            f"{n(r['obs'])} & {r['y0']}--{r['y1']} \\\\\n"
        )

# timeliness: latest year with a value, per national series
lat = num[num["geo_level"] != "district"].groupby(["source_id", "series_code"])["year"].max().reset_index()
lu = lat[lat["source_id"] == "UN_SDG_API"]["year"]
mac("unLatestMedian", str(int(np.median(lu))), int(np.median(lu)))
for yr in (2020, 2022):
    c = int((lu >= yr).sum())
    mac(f"unLatestSince{'Twenty' if yr == 2020 else 'TwentyTwo'}", n(c), c)
    mac(f"unLatestSince{'Twenty' if yr == 2020 else 'TwentyTwo'}Pct", f(100 * c / len(lu), 0), 100 * c / len(lu))
mac("unOldest", str(int(lu.min())))
nyears = num[num["geo_level"] != "district"].groupby(["source_id", "series_code"])["year"].nunique().reset_index()
nu = nyears[nyears["source_id"] == "UN_SDG_API"]["year"]
mac("unYearsMedian", str(int(np.median(nu))), float(np.median(nu)))
mac("unSingleYear", n((nu == 1).sum()), int((nu == 1).sum()))
mac("unSingleYearPct", f(100 * (nu == 1).mean(), 0), 100 * (nu == 1).mean())
nm = nyears[nyears["source_id"] == "MOSPI_NIF_2025"]["year"]
mac("moYearsMedian", str(int(np.median(nm))), float(np.median(nm)))
mac("moFewYears", n((nm < 3).sum()), int((nm < 3).sum()))
mac("moFewYearsPct", f(100 * (nm < 3).mean(), 0), 100 * (nm < 3).mean())
nall = pd.concat([nu, nm])
mac("natFewYears", n((nall < 3).sum()), int((nall < 3).sum()))
mac("natSeriesTotal", n(len(nall)), len(nall))
mac("natFewYearsPct", f(100 * (nall < 3).mean(), 0), 100 * (nall < 3).mean())

# city breakdowns
city = obs[
    (obs["value_status"] != "not_available") & obs["dimensions"].astype(str).str.contains('"Cities"', regex=False)
]
mac("cityObs", n(len(city)), len(city))
mac("cityN", n(city["dimensions"].map(lambda d: json.loads(d).get("Cities")).nunique()))
mac("citySeries", n(city["series_code"].nunique()))

# MoSPI not-parsed reasons
mnp = np_[np_["source_id"] == "MOSPI_NIF_2025"].copy()
mnp["r"] = mnp["reason"].str.replace(r" \(e\.g\..*", "", regex=True)
with open(OUT / "tab_mospi_np.tex", "w") as fh:
    for reason, c in mnp["r"].value_counts().items():
        fh.write(f"{tex_escape(reason[0].upper() + reason[1:])} & {c} \\\\\n")
assert len(mnp) == mo["indicators_not_parsed"]

# ------------------------------------------------------------------ NITI SDG India Index
latest = scores[(scores["edition"] == "2023-24") & (scores["goal"] == 0) & (scores["geo_level"] != "national")]
mac("nitiN", str(len(latest)))
mx, mn = latest["score"].max(), latest["score"].min()
mac("nitiMax", str(int(mx)))
mac("nitiMin", str(int(mn)))
mac("nitiTop", tex_escape(" and ".join(sorted(latest.loc[latest["score"] == mx, "geography"]))))
mac("nitiBottom", tex_escape(" and ".join(sorted(latest.loc[latest["score"] == mn, "geography"]))))
fr = int((latest["score"] >= 65).sum())
mac("nitiFront", str(fr))
mac("nitiPerformer", str(int(((latest["score"] >= 50) & (latest["score"] < 65)).sum())))
assert ((latest["score"] < 50).sum()) == 0
natc = scores[(scores["geo_id"] == "IN") & (scores["goal"] == 0)].sort_values("edition")
for e, s in zip(natc["edition"], natc["score"], strict=True):
    mac("india" + {"2018": "A", "2019-20": "B", "2020-21": "C", "2023-24": "D"}[e], str(int(s)))
ig = scores[(scores["geo_id"] == "IN") & (scores["goal"] > 0) & (scores["edition"] == "2023-24")]
mac("nitiGoalScores", str(len(ig)))
gmax, gmin = ig.loc[ig["score"].idxmax()], ig.loc[ig["score"].idxmin()]
mac("indiaGoalMax", str(int(gmax.goal)))
mac("indiaGoalMaxScore", str(int(gmax.score)))
mac("indiaGoalMin", str(int(gmin.goal)))
mac("indiaGoalMinScore", str(int(gmin.score)))
mac("nitiRows", str(len(scores)))

# ------------------------------------------------------------------ districts: NFHS
dd = obs[obs["geo_level"] == "district"]
mac("nDistricts", n(dd["geo_id"].nunique()), dd["geo_id"].nunique())
mac("nDistStates", str(dd["geo_id"].str.rsplit(".", n=1).str[0].nunique()))
mac("nNfhsSeries", str(dd["series_code"].nunique()))
mac("nNfhsGoals", str(dd["goal"].nunique()))
br = dd["value_raw"].astype(str).str.fullmatch(r"\(.*\)")
mac("nBracket", n(br.sum()), int(br.sum()))
nfhs_np = np_[np_["source_id"] == "NFHS5_DISTRICTS"]
nst = man["source_status"]["NFHS5_DISTRICTS"]
mac("nfhsSheets", n(nst["fact_sheets"]), nst["fact_sheets"])
mac("nfhsRenumbered", str(nst["sheets_with_source_numbering_errors_corrected_by_name"]))
sk = nfhs_np[nfhs_np["kind"] == "skipped"]
cells = sk["reason"].str.extract(r"\[([\d, ]+)\]")[0].str.split(",").map(len)
mac("nfhsSkippedCells", str(int(cells.sum())))
mac("nfhsSkippedSheets", str(sk["code"].nunique()))
# independent digitisation (pratapvardhan/NFHS-5, CC BY 4.0):
# exact comparison on State, district, indicator number and round
if len(sys.argv) > 2:
    import unicodedata

    pv = pd.read_csv(sys.argv[2])
    pv["num"] = pv["Indicator"].str.extract(r"^(\d+)\.")[0].astype(float)
    key = lambda x: re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", str(x).lower()))  # noqa: E731
    d2 = dd.copy()
    d2["num"] = d2["series_code"].str.extract(r"NFHS_D(\d+)")[0].astype(float)
    d2["rnd"] = d2["time_period"].str[:6]
    d2["dk"] = d2["geography"].map(key)
    d2["st"] = d2["geo_id"].str.split(".").str[1].replace({"DH": "DD", "LA": "LH", "TS": "TG"})
    pv["dk"] = pv["District"].map(key)
    pl = pd.concat(
        [
            pv[["State-Code", "dk", "num", c]].rename(columns={"State-Code": "st", c: "pv"}).assign(rnd=c)
            for c in ("NFHS-5", "NFHS-4")
        ]
    )
    mm = d2.merge(pl, on=["st", "dk", "num", "rnd"])
    mm = mm[mm["value_status"] == "numeric"]
    mm["pvn"] = pd.to_numeric(mm["pv"], errors="coerce")
    mm = mm[mm["pvn"].notna()]
    same = mm["value"].round(2) == mm["pvn"].round(2)
    diff = mm[~same]
    mac("pvShared", n(len(mm)), len(mm))
    mac("pvSame", n(int(same.sum())), int(same.sum()))
    mac("pvDiff", str(int((~same).sum())))
    mac("pvDistricts", str(mm["geo_id"].nunique()))
    mac("pvTheirDistricts", str(pv.groupby(["State-Code", "District"]).ngroups))
    mac("pvDiffDistricts", tex_escape(", ".join(sorted(diff["geography"].unique()))))

# ------------------------------------------------------------------ districts: NITI MPI and Aspirational
pct = lambda v: None if v in ("", "–", "-") else float(str(v).rstrip("%"))  # noqa: E731
mac("mpiRows", str(len(mpi_x)))
mpi_np = pd.read_csv(R / "niti_mpi_2023_districts_not_parsed.csv", dtype=str, keep_default_na=False)
mac("mpiStray", str(len(mpi_np)))
ctx["h5"] = ctx["mpi_hcr_nfhs5"].map(lambda v: pct(v) if isinstance(v, str) else None)
ctx["h4"] = ctx["mpi_hcr_nfhs4"].map(lambda v: pct(v) if isinstance(v, str) else None)
mac("mpiMatched", str(int(ctx["h5"].notna().sum())))
aliases = pd.read_csv(R / "niti_mpi_district_aliases.csv")
mac("mpiAliases", str(len(aliases)))
mac("mpiUnmatched", str(len(mpi_x) - int(ctx["h5"].notna().sum())))
mac("hMedFive", f(ctx["h5"].median(), 2), ctx["h5"].median())
# NFHS publishes no NFHS-4 value for districts whose boundary changed; NITI's NFHS-4 figure for
# them refers to the old district, so they are left out of every comparison between rounds
no4 = {d[0] for i, d in enumerate(dist["districts"]) if all(s["r4"][i] is None for s in dist["series"])}
boundary = ctx["geo_id"].isin(no4) & ctx["h4"].notna()
mac("hOtherBoundary", str(int(boundary.sum())))
pair = ctx[~boundary].dropna(subset=["h4", "h5"])
mac("hPairN", str(len(pair)))
mac("hMedFourPair", f(pair["h4"].median(), 2), pair["h4"].median())
mac("hMedFivePair", f(pair["h5"].median(), 2), pair["h5"].median())
mac("hDeclined", str(int((pair["h5"] < pair["h4"]).sum())))
mac("hRose", str(int((pair["h5"] > pair["h4"]).sum())))
mac("hSame", str(int((pair["h5"] == pair["h4"]).sum())))
q = ctx["h5"].quantile([0.2, 0.4, 0.6, 0.8])
v = np.sort(ctx["h5"].dropna().to_numpy())
nn = len(v)
cuts = [v[int(math.floor(k * nn / 5))] for k in (1, 2, 3, 4)]
band = np.array([sum(x >= c for c in cuts) for x in ctx["h5"]])
ctx["band"] = band
for b, word in enumerate(["One", "Two", "Three", "Four", "Five"]):
    sel = ctx[ctx["band"] == b]["h5"]
    mac(f"band{word}Lo", f(sel.min(), 2))
    mac(f"band{word}Hi", f(sel.max(), 2))
    mac(f"band{word}N", str(len(sel)))
hmax = ctx.loc[ctx["h5"].idxmax()]
hmin_n = int((ctx["h5"] == ctx["h5"].min()).sum())
names = dict((d[0], d[1]) for d in dist["districts"])
stn = dist["states"]
mac("hMaxDistrict", tex_escape(names[hmax.geo_id]))
mac("hMaxState", tex_escape(stn[hmax.geo_id.rsplit(".", 1)[0]]))
mac("hMax", f(hmax.h5, 2))
mac("hMin", f(ctx["h5"].min(), 2))
mac("hMinN", str(hmin_n))
mac("aspListed", str(len(asp_x)))
mac("aspMatched", str(int(ctx["aspirational"].fillna(False).astype(bool).sum())))
asp = ctx["aspirational"].fillna(False).astype(bool)
mac("aspMedH", f(ctx.loc[asp, "h5"].median(), 2))
mac("othMedH", f(ctx.loc[~asp, "h5"].median(), 2))
mac("othN", str(int((~asp).sum())))
ap = ctx.loc[asp, "band"]
mac("aspInPoorest", str(int((ap == 4).sum())))
mac("aspInTopTwo", str(int((ap >= 3).sum())))
mac("aspInLeastPoor", str(int((ap == 0).sum())))
mw = stats.mannwhitneyu(ctx.loc[asp, "h5"].dropna(), ctx.loc[~asp, "h5"].dropna(), alternative="two-sided")
auc = mw.statistic / (asp.sum() * (~asp).sum())
mac("aspAUC", f(auc, 2), auc)

# ------------------------------------------------------------------ district association table
MPI_PARTS = {
    "NFHS_D007",
    "NFHS_D008",
    "NFHS_D009",
    "NFHS_D010",
    "NFHS_D033",
    "NFHS_D045",
    "NFHS_D073",
    "NFHS_D076",
    "NFHS_D078",
}
ids = [d[0] for d in dist["districts"]]
H = np.array([ctx.set_index("geo_id").at[g, "h5"] for g in ids], dtype=float)
recs = []
for s in dist["series"]:
    v5 = np.array([np.nan if x is None else x for x in s["v5"]], dtype=float)
    v4 = np.array([np.nan if x is None else x for x in s["v4"]], dtype=float)
    ok = ~np.isnan(v5) & ~np.isnan(H)
    rho = stats.spearmanr(H[ok], v5[ok]).statistic
    nn = int(ok.sum())
    se = math.sqrt((1 + rho**2 / 2) / (nn - 3))  # Bonett and Wright (2000)
    z = math.atanh(rho)
    lo, hi = math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)
    pr = ~np.isnan(v5) & ~np.isnan(v4)
    ch = v5[pr] - v4[pr]
    recs.append(
        {
            "code": s["code"],
            "label": s["label"],
            "goal": s["goal"],
            "unit": s["unit"],
            "n5": int((~np.isnan(v5)).sum()),
            "med5": float(np.nanmedian(v5)),
            "npair": int(pr.sum()),
            "medch": float(np.median(ch)) if len(ch) else None,
            "q1": float(np.quantile(ch, 0.25)) if len(ch) else None,
            "q3": float(np.quantile(ch, 0.75)) if len(ch) else None,
            "rho": rho,
            "lo": lo,
            "hi": hi,
            "n": nn,
            "part": s["code"] in MPI_PARTS,
        }
    )
A = pd.DataFrame(recs).sort_values("rho")
mac("nIndAssoc", str(len(A)))
comp, other = A[A["part"]], A[~A["part"]]
mac("nComp", str(len(comp)))
mac("rhoCompMin", f(comp["rho"].abs().min(), 2))
mac("rhoCompMax", f(comp["rho"].abs().max(), 2))
top_other = other.reindex(other["rho"].abs().sort_values(ascending=False).index)
for k, word in enumerate(["One", "Two", "Three"]):
    r = top_other.iloc[k]
    mac(f"otherTop{word}", tex_escape(r["label"][0].lower() + r["label"][1:]))
    mac(f"otherTop{word}Rho", f(r["rho"], 2), r["rho"])
weak = other[other["rho"].abs() < 0.2]
mac("nWeak", str(len(weak)))
mac("nStrongAll", str(int((A["rho"].abs() >= 0.5).sum())))
with open(OUT / "tab_assoc.tex", "w") as fh:
    for r in A.sort_values(["goal", "code"]).itertuples():
        mark = r"$^\dagger$" if r.part else ""
        fh.write(
            f"{r.goal} & {tex_escape(r.label)}{mark} & {r.n5} & {r.med5:.1f} & {r.npair} & "
            f"{change_cell(r)} & "
            f"{f(r.rho, 2)} [{f(r.lo, 2)}, {f(r.hi, 2)}] \\\\\n"
        )
A.to_csv(OUT / "district_associations.csv", index=False)

# ------------------------------------------------------------------ figures
# Fig 1: share of UN series with India data, by goal
fig, ax = plt.subplots(figsize=(6.4, 3.0))
ax.bar(cov["goal"], cov["share"], color=[GC[g] for g in cov["goal"]], width=0.75)
for r in cov.itertuples():
    ax.text(r.goal, r.share + 1.5, f"{r.withd}/{r.listed}", ha="center", fontsize=6.3, color="#333")
ax.set_xticks(range(1, 18))
ax.set_xlabel("SDG")
ax.set_ylabel("UN series with at least one\nnumeric value for India (%)")
ax.set_ylim(0, 110)
ax.axhline(100, color="#bbb", lw=0.6, ls=":")
fig.tight_layout()
fig.savefig(OUT / "fig_un_coverage.pdf")
plt.close(fig)

# Fig 2: national series with a value, by year
natn = num[num["geo_level"] != "district"]
yr = natn.groupby(["year", "source_id"])["series_code"].nunique().unstack(fill_value=0)
yr = yr[(yr.index >= 1990)]
fig, ax = plt.subplots(figsize=(6.4, 2.6))
ax.plot(
    yr.index,
    yr.get("UN_SDG_API", 0),
    color="#19486a",
    lw=1.8,
    marker="o",
    ms=2.5,
    label="UN Global SDG Indicators Database",
)
ym = yr["MOSPI_NIF_2025"][yr.index >= int(natn.loc[natn["source_id"] == "MOSPI_NIF_2025", "year"].min())]
ax.plot(ym.index, ym, color="#c5192d", lw=1.8, marker="o", ms=2.5, label="MoSPI NIF Progress Report 2025")
ax.set_xlabel("Observation year")
ax.set_ylabel("Series with a value")
ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.set_ylim(0, None)
ax.grid(axis="y", color="#eee")
fig.tight_layout()
fig.savefig(OUT / "fig_years.pdf")
plt.close(fig)
peak = yr.get("UN_SDG_API").idxmax()
mac("unPeakYear", str(int(peak)))
mac("unPeakN", str(int(yr["UN_SDG_API"].max())))

# Fig 3: NITI composite by State/UT
lt = latest.sort_values("score")
fig, ax = plt.subplots(figsize=(6.4, 6.2))
cols = ["#19486a" if g == "state" else "#7fa7c4" for g in lt["geo_level"]]
ax.barh(lt["geography"], lt["score"], color=cols, height=0.72)
for i, r in enumerate(lt.itertuples()):
    ax.text(r.score + 0.6, i, str(int(r.score)), va="center", fontsize=7)
ax.set_xlim(0, 100)
ax.set_xlabel("SDG India Index 2023--24 composite score (0--100)".replace("--", "–"))
ax.tick_params(axis="y", labelsize=7.3)
ax.axvline(65, color="#999", lw=0.7, ls="--")
ax.text(64.5, len(lt) - 0.2, "Front Runner (65+)", fontsize=7, color="#555", ha="right", va="bottom")
from matplotlib.patches import Patch  # noqa: E402

ax.legend(
    handles=[Patch(color="#19486a", label="State"), Patch(color="#7fa7c4", label="Union Territory")],
    frameon=False,
    fontsize=8,
    loc="lower right",
    bbox_to_anchor=(1.0, 1.0),
    ncol=2,
)
ax.set_ylim(-0.8, len(lt) + 0.8)
fig.tight_layout()
fig.savefig(OUT / "fig_niti.pdf")
plt.close(fig)

# Fig 4: Spearman rho with 95% CI, district level
B = A.sort_values("rho")
fig, ax = plt.subplots(figsize=(6.4, 7.0))
y = np.arange(len(B))
ax.errorbar(B["rho"], y, xerr=[B["rho"] - B["lo"], B["hi"] - B["rho"]], fmt="none", ecolor="#999", lw=1)
ax.scatter(
    B["rho"],
    y,
    c=[GC[g] for g in B["goal"]],
    s=[34 if p else 30 for p in B["part"]],
    marker="o",
    edgecolors=[INK if p else "white" for p in B["part"]],
    linewidths=[1.4 if p else 0.5 for p in B["part"]],
    zorder=3,
)
ax.set_yticks(y)
ax.set_yticklabels(
    [
        (lbl[:58] + "…" if len(lbl) > 59 else lbl) + (" †" if p else "")
        for lbl, p in zip(B["label"], B["part"], strict=True)
    ],
    fontsize=6.8,
)
ax.axvline(0, color="#666", lw=0.8)
ax.set_xlim(-1, 1)
ax.set_xlabel("Spearman's ρ (95% CI)")
ax.grid(axis="x", color="#eee")
fig.tight_layout()
fig.savefig(OUT / "fig_assoc.pdf")
plt.close(fig)

# Fig 5: MPI headcount NFHS-4 vs NFHS-5 by district
fig, ax = plt.subplots(figsize=(4.2, 4.0))
ax.scatter(
    pair["h4"], pair["h5"], s=7, color=np.where(asp.loc[pair.index], "#c98a0b", "#19486a"), alpha=0.7, linewidths=0
)
ax.plot([0, 80], [0, 80], color="#999", lw=0.8, ls="--")
ax.set_xlim(0, 80)
ax.set_ylim(0, 80)
ax.set_aspect("equal")
ax.set_xlabel("Headcount ratio, NFHS-4 2015–16 (%)")
ax.set_ylabel("Headcount ratio, NFHS-5 2019–21 (%)")
ax.legend(
    handles=[Patch(color="#c98a0b", label="Aspirational District"), Patch(color="#19486a", label="Other district")],
    frameon=False,
    fontsize=7.5,
    loc="upper left",
)
fig.tight_layout()
fig.savefig(OUT / "fig_mpi.pdf")
plt.close(fig)

# ------------------------------------------------------------------ write
(OUT / "stats.tex").write_text(
    "% Generated by make_stats.py from the SDG Explorer India data. Do not edit by hand.\n"
    + "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in M.items())
    + "\n"
)
(OUT / "numbers.json").write_text(json.dumps(NUM, indent=1, default=float))
print(len(M), "macros written")

# ------------------------------------------------------------------ late additions (build metadata, tests)
import subprocess  # noqa: E402

M2 = {}
mac("buildDate", man["built_at"][:10])
w = [x for x in man["validation"]["warnings"] if "outside 0-100" in x]
po = obs[obs["unit"].astype(str).str.upper().eq("PERCENT") & obs["value"].notna() & ~obs["value"].between(0, 100)]
assert w and int(re.match(r"(\d+)", w[0]).group(1)) == len(po)
mac("pctOutside", str(len(po)))
mac("pctOutsideSeries", str(po["series_code"].nunique()))
mac("valErrors", str(len(man["validation"]["errors"])))
rel = ind["release"].astype(str).value_counts()
mac("unRelease", tex_escape(rel.index[0]))
col = subprocess.run(
    [sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=REPO, capture_output=True, text=True
).stdout
m_ = re.search(r"(\d+) tests? collected", col)
mac("nTests", m_.group(1) if m_ else "--")
mac("nTestFiles", str(len(list((REPO / "tests").glob("test_*.py")))))
(OUT / "stats.tex").write_text(
    "% Generated by make_stats.py from the SDG Explorer India data. Do not edit by hand.\n"
    + "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in M.items())
    + "\n"
)
(OUT / "numbers.json").write_text(json.dumps(NUM, indent=1, default=float))
print(len(M), "macros written (final)")
