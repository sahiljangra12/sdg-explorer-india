"""SDG Explorer India: Streamlit dashboard over the verified, processed tables.

Run from the project folder:  streamlit run app/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sdg_india import config, geo  # noqa: E402
from sdg_india.io import explode_by_indicator, read_observations  # noqa: E402

st.set_page_config(page_title="SDG Explorer India", page_icon="📊", layout="wide")

PROC = config.PROCESSED
ACCENT, INK2 = "#1b6e8a", "#5a5955"
GOAL_COLORS = {1: "#E5243B", 2: "#DDA63A", 3: "#4C9F38", 4: "#C5192D", 5: "#FF3A21", 6: "#26BDE2", 7: "#FCC30B",
               8: "#A21942", 9: "#FD6925", 10: "#DD1367", 11: "#FD9D24", 12: "#BF8B2E", 13: "#3F7E44", 14: "#0A97D9",
               15: "#56C02B", 16: "#00689D", 17: "#19486A"}   # official UN SDG goal colours
LAYOUT = dict(template="simple_white", font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", size=13),
              margin=dict(l=10, r=10, t=40, b=10), hoverlabel=dict(font_size=12))

st.markdown("""<style>
.block-container{padding-top:1.6rem}
[data-testid="stMetricValue"]{font-size:1.7rem}
.note{color:#5a5955;font-size:.9rem;line-height:1.45}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.78rem;font-weight:600;margin-right:6px}
.verified{background:#e3f2ea;color:#1b6e3a}.composite{background:#fdf0dc;color:#8a5a00}.missing{background:#f3f3f1;color:#5a5955}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data
@st.cache_data(show_spinner=False)
def load(proc: str):
    proc = Path(proc)

    def csv(name):
        f = proc / name
        try:
            return pd.read_csv(f, low_memory=False) if f.exists() and f.stat().st_size > 2 else pd.DataFrame()
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    obs = read_observations(proc / "observations.csv")
    # one row per observation and linked indicator, so each series appears under every goal it belongs to
    obs = explode_by_indicator(obs) if not obs.empty else obs
    manifest = json.loads((proc / "manifest.json").read_text()) if (proc / "manifest.json").exists() else {}
    return obs, csv("indicators.csv"), csv("coverage.csv"), csv("index_scores.csv"), csv("sources.csv"), \
        csv("not_parsed.csv"), manifest, geo.load()


obs, indicators, cov, scores, sources, not_parsed, manifest, geojson = load(str(PROC))
goal_label = lambda g: f"SDG {int(g)}: {config.GOALS[int(g)]}"  # noqa: E731


CODE_LABELS = {"BOTHSEX": "Both sexes", "FEMALE": "Female", "MALE": "Male", "ALLAREA": "All areas", "URBAN": "Urban",
               "RURAL": "Rural", "ALLAGE": "All ages", "_T": "Total", "TOTAL": "Total", "ALL": "All", "_O": "Other",
               "_X": "Not applicable", "_U": "Unknown", "PRIMAR": "Primary", "LOWSEC": "Lower secondary",
               "UPPSEC": "Upper secondary", "SECOND": "Secondary", "PREPRI": "Pre-primary", "CITY": "Cities",
               "TSUB": "Towns and suburbs", "Q1": "Poorest 20%", "Q5": "Richest 20%"}
TOTALS = {"BOTHSEX", "ALLAREA", "ALLAGE", "_T", "TOTAL", "ALL", "ALLDOMAINS", "DRUG_TOTAL"}
UNIT_LABELS = {"PERCENT": "%", "NUMBER": "Number", "PER_1000_LIVE_BIRTHS": "Per 1,000 live births",
               "PER_100000_LIVE_BIRTHS": "Per 100,000 live births", "PER_100000_POP": "Per 100,000 population",
               "PER_1000_POP": "Per 1,000 population", "PER_1000_UNINFECTED_POP": "Per 1,000 uninfected population",
               "CU_USD": "Current US$", "CON_USD": "Constant US$", "INDEX": "Index", "HA": "Hectares",
               "TONNES": "Tonnes", "KG": "Kilograms", "YEARS": "Years", "RATIO": "Ratio", "SCORE": "Score"}


NATURE = {"C": "Country data", "CA": "Country data, adjusted", "E": "Estimated", "M": "Modelled",
          "G": "Global monitoring data", "N": "Non-relevant", "NA": "Not available"}


def m_src_is_mospi(s: pd.DataFrame) -> bool:
    return bool(len(s)) and s["source_id"].iloc[0].startswith("MOSPI")


def unit_label(u: str) -> str:
    return UNIT_LABELS.get(u, u.replace("_", " ").capitalize() if u else "")


def dims_label(d: str) -> str:
    """Readable breakdown label, e.g. 'Female · Age 15-24 · Rural'; 'Total' when every category is a total."""
    try:
        x = json.loads(d) if d else {}
    except json.JSONDecodeError:
        return d
    parts = []
    for k, v in x.items():
        if str(v).upper() in TOTALS:
            continue
        label = CODE_LABELS.get(v, v)
        parts.append(label if k in ("Sex", "Location") else f"Age {label}" if k == "Age" else f"{k}: {label}")
    return " · ".join(parts) or "Total"


def download(df: pd.DataFrame, name: str, label: str, key: str):
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), name, "text/csv", key=key)


# ---------------------------------------------------------------- header
st.title("SDG Explorer India")
st.markdown('<p class="note">India\'s progress on the 17 Sustainable Development Goals from official sources: '
            'the UN Global SDG Indicators Database, MoSPI\'s National Indicator Framework, NITI Aayog\'s SDG India '
            'Index and the NFHS district fact sheets. Every value links back to its source file. Missing values are '
            'shown as missing, never filled in.'
            '</p>', unsafe_allow_html=True)

tot = manifest.get("totals", {})
k = st.columns(5)
k[0].metric("Observations", f"{tot.get('observations', 0):,}")
k[1].metric("Indicators", f"{tot.get('indicators', 0):,}")
k[2].metric("Data series", f"{tot.get('series', 0):,}")
k[3].metric("Goals with data", f"{len(tot.get('goals_covered', []))} / 17")
k[4].metric("Years", f"{tot['earliest_year']}–{tot['latest_year']}" if tot.get("observations") else "—")

if obs.empty:
    st.warning("No verified indicator observations are loaded yet. In the project folder, run "
               "`python -m sdg_india all` with an internet connection (or `python -m sdg_india import <folder>` for "
               "files downloaded in a browser). The tabs below show what is available now.")

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Filters")
    goals_present = sorted(int(g) for g in obs["goal"].dropna().unique()) if not obs.empty else []
    goal = st.selectbox("Goal", goals_present or list(config.GOALS), format_func=goal_label)
    src_opts = sorted(obs["source_id"].unique()) if not obs.empty else []
    src_sel = st.multiselect("Sources", src_opts, default=src_opts)
    if not obs.empty:
        y0, y1 = int(obs["year"].min()), int(obs["year"].max())
        years = st.slider("Observation years", y0, y1, (y0, y1))
    headline_only = st.toggle("Headline totals only", value=True,
                              help="Show only the 'all people / all areas' row of each series where the source "
                                   "publishes one. Turn off to see breakdowns by sex, age, location and so on.")
    st.divider()
    st.caption(f"Data built {manifest.get('built_at', 'never')[:10]}. "
               "See the Sources tab for retrieval dates and file checksums.")

f = obs
if not obs.empty:
    f = obs[obs["source_id"].isin(src_sel) & obs["year"].between(*years)]

nat_f = f[f["geo_level"] == "national"] if not f.empty else f
dist_all = obs[obs["geo_level"] == "district"] if not obs.empty else obs

tabs = st.tabs(["Indicator explorer", "States & UTs", "Districts", "Missing data", "Goal overview", "Data & downloads",
                "Sources & methods"])

# ---------------------------------------------------------------- 1. indicator explorer
with tabs[0]:
    st.subheader(goal_label(goal))
    g = nat_f[nat_f["goal"] == goal] if not nat_f.empty else nat_f
    n_dist = dist_all[dist_all["goal"] == goal]["series_code"].nunique() if not dist_all.empty else 0
    if n_dist:
        st.caption(f"National series below. {n_dist} more series for this goal are published for districts "
                   "(NFHS-5): see the Districts tab.")
    if g.empty:
        st.info("No observations for this goal in the loaded sources. The Missing data tab lists which indicators "
                "have no India data.")
    else:
        series_tbl = (g.groupby(["indicator_code", "series_code"])
                      .agg(desc=("series_description", "first"), n=("obs_id", "size")).reset_index()
                      .sort_values(["indicator_code", "series_code"]))
        opts = series_tbl.apply(lambda r: f"{r.indicator_code} · {r.desc} [{r.series_code}]", axis=1).tolist()
        pick = st.selectbox(f"Series ({len(opts)} with data for this goal)", opts)
        series = series_tbl.iloc[opts.index(pick)]["series_code"]
        s = g[g["series_code"] == series].copy()
        s["breakdown"] = s["dimensions"].map(dims_label)
        if headline_only and s["headline"].astype(bool).any():
            s = s[s["headline"].astype(bool)]
        breakdowns = sorted(s["breakdown"].unique())
        chosen = st.multiselect("Breakdowns", breakdowns, default=breakdowns[:6],
                                help="Categories published by the source, e.g. sex, age group, urban/rural.")
        s = s[s["breakdown"].isin(chosen)]
        num = s[s["value"].notna()]
        unit = s["unit"].iloc[0] if len(s) else ""
        unit_txt = unit_label(unit) or ("Unit as stated in the series name" if m_src_is_mospi(s) else "")
        if num.empty:
            st.info("This series has no numeric values for the selection (values may be published as ranges such as "
                    "'<0.1', which are shown in the table below).")
        else:
            plot = num[["year", "value", "breakdown", "time_period"]].sort_values("year")
            fig = px.line(plot, x="year", y="value", color="breakdown", markers=True,
                          hover_data={"time_period": True, "breakdown": False},
                          color_discrete_sequence=["#1b6e8a", "#e08e2b", "#7b5ea7", "#3a9a5b", "#c94f4f", "#8a8984"])
            fig.update_traces(line=dict(width=1.2, dash="dot"), marker=dict(size=9, line=dict(width=1, color="white")),
                              hovertemplate="%{x}: %{y:,.4g}<extra>%{fullData.name}</extra>")
            fig.update_layout(**LAYOUT, height=430, legend_title="", yaxis_title=unit_txt,
                              xaxis_title="Observation year", legend=dict(orientation="h", y=-0.18),
                              title=dict(text=s["series_description"].iloc[0], font=dict(size=15)))
            st.plotly_chart(fig, width="stretch")
            yrs = sorted(num["year"].unique())
            missing = (yrs[-1] - yrs[0] + 1) - len(yrs)
            st.caption(f"Each dot is a published value ({len(num)} values, {yrs[0]}–{yrs[-1]}). The dotted line only "
                       "guides the eye between published years; no values are estimated for the "
                       f"{missing} years in between that have no data." if missing > 0 else
                       f"Each dot is a published value ({len(num)} values, {yrs[0]}–{yrs[-1]}).")
        m = s.iloc[0]
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("**About this series**")
            st.markdown(f"- **Indicator:** {m['indicator_code']} (all linked: {m.get('indicator_codes_all', '')})\n"
                        f"- **Series code:** `{series}`  ·  **Unit:** {unit_txt or '—'}  ·  "
                        + (f"**Nature:** {NATURE.get(m.get('nature', ''), m.get('nature', ''))}"
                           if m.get("nature") else "") + "\n"
                        f"- **Original data source:** {m['original_source'] or '—'}\n"
                        f"- **Release:** {m.get('release', '') or '—'}  ·  **Source:** {m['source_id']}")
            notes = sorted({x for x in s["footnotes"] if x})
            if notes:
                with st.expander(f"Footnotes from the source ({len(notes)})"):
                    for n in notes:
                        st.markdown(f"- {n}")
        with c2:
            meta = indicators[indicators["series_code"] == series] if not indicators.empty else pd.DataFrame()
            if not meta.empty:
                st.markdown("**Official indicator definition**")
                st.markdown(f"{meta.iloc[0]['indicator_description']}")
                st.markdown(f"[UN metadata for target {meta.iloc[0]['target']}]({meta.iloc[0]['metadata_url']})")
            st.markdown(f"[{'Report page' if m_src_is_mospi(s) else 'Source request'}]({m['source_url']})")
        cols = ["year", "time_period", "breakdown", "value", "value_raw", "unit", "lower_bound", "upper_bound",
                "original_source", "footnotes", "source_url"]
        st.dataframe(s[[c for c in cols if c in s]].sort_values(["breakdown", "year"]), hide_index=True,
                     width="stretch")
        download(s, f"sdg_india_{series}.csv", "Download this series (CSV)", "dl_series")

# ---------------------------------------------------------------- 2. states and UTs
with tabs[1]:
    st.subheader("States and Union Territories")
    state_obs = f[f["geo_level"].isin(["state", "union_territory"])] if not f.empty else f
    if state_obs.empty:
        st.markdown('<span class="pill missing">No state-level indicator values loaded</span>', unsafe_allow_html=True)
        st.markdown('<p class="note">The UN database and MoSPI\'s NIF report both publish national figures. '
                    'State-level indicator values appear in NITI Aayog\'s report only as a low-resolution scan, which '
                    'cannot be read reliably enough to publish. The NITI Aayog composite scores below are shown '
                    'separately because they are an index, not indicator data.</p>', unsafe_allow_html=True)
    if not scores.empty:
        st.markdown("#### SDG India Index (NITI Aayog)")
        st.markdown('<span class="pill composite">Composite index score, 0–100</span>'
                    '<span class="note">Built by NITI Aayog from normalised, weighted indicators. It summarises '
                    'relative performance; it is not a raw indicator value and is never mixed with them.</span>',
                    unsafe_allow_html=True)
        sc = scores[scores["geo_level"] != "national"]
        ed = st.selectbox("Index edition", sorted(sc["edition"].unique(), reverse=True), key="edition")
        sc = sc[(sc["edition"] == ed) & (sc["goal"] == 0)].sort_values("score")
        a, b = st.columns([1, 1])
        with a:
            if geojson:
                fig = px.choropleth(sc, geojson=geojson, locations="geo_id", featureidkey="properties.geo_id",
                                    color="score", hover_name="geography", color_continuous_scale="Teal",
                                    range_color=(sc["score"].min(), sc["score"].max()))
                fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
                fig.update_layout(**{**LAYOUT, "margin": dict(l=0, r=0, t=0, b=0)}, height=780,
                                  coloraxis_colorbar=dict(title="Score", thickness=12, len=0.5, x=0.92, y=0.3))
                st.plotly_chart(fig, width="stretch")
                st.caption(geojson.get("attribution", ""))
        with b:
            sc = sc.assign(type=sc["geo_level"].map({"state": "State", "union_territory": "Union Territory"}))
            fig = px.bar(sc, x="score", y="geography", orientation="h", color="type", text="score",
                         color_discrete_map={"State": ACCENT, "Union Territory": "#e08e2b"},
                         labels={"type": "", "score": f"Composite score, {ed}", "geography": ""},
                         hover_data={"report_page": True})
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(**{**LAYOUT, "margin": dict(l=10, r=30, t=10, b=10)}, height=780,
                              legend=dict(orientation="h", yanchor="top", y=-0.07, x=0),
                              yaxis=dict(categoryorder="array", categoryarray=sc["geography"].tolist(), dtick=1,
                                         tickfont=dict(size=11)), xaxis=dict(range=[0, 100]))
            st.plotly_chart(fig, width="stretch")
        nat = scores[(scores["geo_id"] == "IN") & (scores["goal"] == 0)].sort_values("edition")
        if not nat.empty:
            st.markdown("**India's composite score by edition**")
            fig = px.line(nat, x="edition", y="score", markers=True, text="score")
            fig.update_traces(textposition="top center", line_color=ACCENT)
            fig.update_layout(**LAYOUT, height=260, yaxis_range=[40, 100], xaxis_title="Index edition",
                              yaxis_title="Score")
            st.plotly_chart(fig, width="stretch")
        ng = scores[(scores["geo_id"] == "IN") & (scores["goal"] > 0)].copy()
        if not ng.empty:
            st.markdown("**India's goal scores by edition**")
            ng["Goal"] = ng["goal"].map(lambda x: f"SDG {x}")
            order = ["2018", "2019-20", "2020-21", "2023-24"]
            fig = px.bar(ng, x="Goal", y="score", color="edition", barmode="group",
                         category_orders={"edition": order, "Goal": [f"SDG {g}" for g in range(1, 18)]},
                         color_discrete_sequence=["#c9d9dd", "#8fb3bd", "#4f8a99", ACCENT],
                         labels={"score": "Goal score (0–100)", "edition": "Edition", "Goal": ""})
            fig.update_layout(**LAYOUT, height=360, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, width="stretch")
            st.caption("Goals 14 and 17 are not scored for India in the report table; Goals 12 and 13 were not scored "
                       "in 2018. Missing bars are missing scores, not zero.")
        n_ver = int(scores["verification"].astype(str).str.startswith("verified").sum())
        st.caption(f"{n_ver} of {len(scores)} index values verified against the report (pages "
                   f"{', '.join(map(str, sorted(scores['report_page'].dropna().astype(int).unique())))}); the "
                   "'verification' column in the download says how each one was checked.")
        download(scores, "niti_sdg_india_index_scores.csv", "Download index scores (CSV)", "dl_scores")

# ---------------------------------------------------------------- 3. districts
with tabs[2]:
    st.subheader("Districts")
    if dist_all.empty:
        st.info("No district-level data loaded.")
    else:
        st.markdown('<p class="note">National Family Health Survey district fact sheets (Ministry of Health and '
                    'Family Welfare / IIPS): NFHS-5 (2019-21) and NFHS-4 (2015-16), for indicators with a clear '
                    'SDG counterpart. Survey estimates for districts have sampling error; values in brackets in '
                    'the fact sheets are based on 25-49 cases, and "na" or "*" mean no estimate.</p>',
                    unsafe_allow_html=True)
        d = dist_all.drop_duplicates(["obs_id"])
        series = (d.groupby("series_code").agg(desc=("series_description", "first"), goal=("goal", "first"))
                  .reset_index().sort_values(["goal", "series_code"]))
        labels = {r.series_code: f"SDG {r.goal} · {r.desc.replace('[NFHS district] ', '')}"
                  for r in series.itertuples()}
        c1, c2 = st.columns([2, 1])
        by_label = {v: k for k, v in labels.items()}
        sc_pick = by_label[c1.selectbox("Indicator", list(by_label), key="d_ind")]
        geos_d = pd.read_csv(PROC / "geographies.csv") if (PROC / "geographies.csv").exists() else pd.DataFrame()
        sel = d[d["series_code"] == sc_pick].copy()
        sel["state_id"] = sel["geo_id"].str.rsplit(".", n=1).str[0]
        state_names = {g: n for g, n in zip(geos_d.get("geo_id", []), geos_d.get("geography", []),
                                                        strict=True)}
        states = sorted(sel["state_id"].unique(), key=lambda x: state_names.get(x, x))
        state_by_name = {state_names.get(x, x): x for x in states}
        st_pick = c2.selectbox("State / UT", ["All India"] + list(state_by_name), key="d_state")
        st_pick = state_by_name.get(st_pick, st_pick)
        sel["round"] = sel["time_period"].str.split().str[0]
        rows5 = sel[sel["round"] == "NFHS-5"]
        n_na = int((rows5["value_status"] == "not_available").sum())
        meta_note = sel["footnotes"].iloc[0].split(" | ")[1] if len(sel) else ""
        if st_pick == "All India":
            v5 = rows5[rows5["value"].notna()]
            fig = px.histogram(v5, x="value", nbins=40, color_discrete_sequence=[ACCENT])
            fig.update_layout(**LAYOUT, height=320, xaxis_title=f"{labels[sc_pick].split(' · ', 1)[1]} — NFHS-5",
                              yaxis_title="Number of districts", bargap=0.05)
            st.plotly_chart(fig, width="stretch")
            st.caption(f"{len(v5)} districts with an NFHS-5 estimate; {n_na} without. {meta_note}.")
            a, b = st.columns(2)
            show = v5.sort_values("value")[["geography", "state_id", "value"]]
            show["state"] = show["state_id"].map(state_names)
            a.markdown("**Lowest 15 districts**")
            a.dataframe(show.head(15)[["geography", "state", "value"]], hide_index=True, width="stretch")
            b.markdown("**Highest 15 districts**")
            b.dataframe(show.tail(15).iloc[::-1][["geography", "state", "value"]], hide_index=True, width="stretch")
        else:
            ss = sel[sel["state_id"] == st_pick]
            wide = ss.pivot_table(index="geography", columns="round", values="value", aggfunc="first")
            wide = wide.reindex(columns=["NFHS-4", "NFHS-5"]).sort_values("NFHS-5", na_position="first")
            fig = go.Figure()
            for name, row in wide.iterrows():
                if pd.notna(row["NFHS-4"]) and pd.notna(row["NFHS-5"]):
                    fig.add_trace(go.Scatter(x=[row["NFHS-4"], row["NFHS-5"]], y=[name, name], mode="lines",
                                             line=dict(color="#c9d9dd", width=3), showlegend=False,
                                             hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=wide["NFHS-4"], y=wide.index, mode="markers", name="NFHS-4 (2015-16)",
                                     marker=dict(size=9, color="white", line=dict(color=ACCENT, width=2))))
            fig.add_trace(go.Scatter(x=wide["NFHS-5"], y=wide.index, mode="markers", name="NFHS-5 (2019-21)",
                                     marker=dict(size=10, color=ACCENT)))
            fig.update_layout(**LAYOUT, height=max(320, 24 * len(wide) + 80), legend=dict(orientation="h", y=1.04),
                              xaxis_title=labels[sc_pick].split(" · ", 1)[1], yaxis=dict(dtick=1, title=""))
            st.plotly_chart(fig, width="stretch")
            st.caption(f"{state_names.get(st_pick, st_pick)}: {len(wide)} districts. Hollow = NFHS-4, filled = NFHS-5. "
                       "Districts formed after 2015-16 have no NFHS-4 estimate. " + meta_note + ".")
            show = ss[["geography", "time_period", "value", "value_raw", "footnotes", "raw_file"]].sort_values(
                ["geography", "time_period"])
            st.dataframe(show, hide_index=True, width="stretch")
        download(sel.drop(columns=["state_id", "round"]), f"nfhs_districts_{sc_pick}.csv",
                 "Download this indicator for all districts (CSV)", "dl_dist")

with tabs[3]:
    st.subheader("What data exists, and what is missing")
    if indicators.empty:
        st.info("The UN indicator list has not been downloaded, so missing indicators cannot be listed yet.")
    else:
        ind = indicators.drop_duplicates(["goal", "series_code"])
        per_goal = ind.groupby("goal").agg(series=("series_code", "nunique"),
                                           with_data=("has_india_data", "sum")).reset_index()
        per_goal["without_data"] = per_goal["series"] - per_goal["with_data"]
        per_goal["label"] = per_goal["goal"].map(lambda x: f"SDG {x}")
        fig = go.Figure([go.Bar(y=per_goal["label"], x=per_goal["with_data"], name="Series with India data",
                                orientation="h", marker_color=ACCENT),
                         go.Bar(y=per_goal["label"], x=per_goal["without_data"], name="No India data",
                                orientation="h", marker_color="#d9d8d3")])
        fig.update_layout(**LAYOUT, barmode="stack", height=520, yaxis=dict(autorange="reversed"),
                          xaxis_title="UN data series (global list)", legend=dict(orientation="h", y=1.06))
        st.plotly_chart(fig, width="stretch")
        st.caption("Counted against every series in the UN global indicator list. Some series do not apply to India "
                   "(for example, small-island or landlocked-country indicators).")
    if tot.get("not_available_markers"):
        st.markdown(f"**Published 'not available' markers:** {tot['not_available_markers']:,} records in which the "
                    "publisher states that no value is available (for example 'NaN = Not Available'). They are listed "
                    "in the coverage table and excluded from observation counts.")
    if not f.empty:
        st.markdown(f"**Years with data, {goal_label(goal)}** (headline rows)")
        g = f[(f["goal"] == goal) & f["value"].notna()]
        g = g[g["headline"].astype(bool)] if g["headline"].astype(bool).any() else g
        if not g.empty:
            grid = g.groupby(["series_code", "year"]).size().unstack(fill_value=0).clip(upper=1)
            grid = grid.reindex(columns=range(int(grid.columns.min()), int(grid.columns.max()) + 1), fill_value=0)
            labels = g.groupby("series_code")["series_description"].first().str.slice(0, 70)
            fig = px.imshow(grid.values, x=[str(c) for c in grid.columns], y=[f"{s} · {labels[s]}" for s in grid.index],
                            color_continuous_scale=[[0, "#f1f1ef"], [1, ACCENT]], aspect="auto")
            fig.update_layout(**LAYOUT, height=max(260, 22 * len(grid)), coloraxis_showscale=False,
                              xaxis_title="Year", yaxis_title="")
            fig.update_traces(hovertemplate="%{y}<br>%{x}: %{z}<extra></extra>", xgap=1, ygap=1)
            st.plotly_chart(fig, width="stretch")
            st.caption("Filled = at least one value that year. Empty cells are years with no published value.")
    if not cov.empty:
        st.markdown("**Coverage of every series**")
        show = cov[cov["goal"] == goal] if "goal" in cov else cov
        st.dataframe(show, hide_index=True, width="stretch")
        download(cov, "sdg_india_coverage.csv", "Download coverage table (CSV)", "dl_cov")
    np_mospi = not_parsed[not_parsed["source_id"] == "MOSPI_NIF_2025"] if not not_parsed.empty else not_parsed
    np_nfhs = not_parsed[not_parsed["source_id"] == "NFHS5_DISTRICTS"] if not not_parsed.empty else not_parsed
    if not np_mospi.empty:
        npg = np_mospi[np_mospi["goal"] == goal]
        with st.expander(f"MoSPI national indicators not parsed for {goal_label(goal)} ({len(npg)} of "
                         f"{len(np_mospi)} overall)"):
            st.caption("These tables in MoSPI's report were not turned into data because their layout could not be "
                       "read without guessing, or because the report gives no values. See the report page shown.")
            st.dataframe(npg[["code", "name", "reason", "page"]], hide_index=True, width="stretch")
    if not np_nfhs.empty:
        with st.expander(f"NFHS district fact sheets: values not read or corrected ({len(np_nfhs)})"):
            st.caption("District values whose numbers were split across lines out of column order were left out "
                       "rather than guessed. Two official fact sheets skip a number in their indicator list; their "
                       "values were matched to indicators by name instead.")
            st.dataframe(np_nfhs[["code", "reason", "kind"]].rename(columns={"code": "fact sheet"}),
                         hide_index=True, width="stretch")
    if not indicators.empty:
        nod = indicators[(indicators["goal"] == goal) & ~indicators["has_india_data"].astype(bool)]
        with st.expander(f"Series in the UN list with no India data for {goal_label(goal)} ({len(nod)})"):
            st.dataframe(nod[["indicator_code", "series_code", "series_description", "tier"]], hide_index=True,
                         width="stretch")

# ---------------------------------------------------------------- 4. goal overview
with tabs[4]:
    st.subheader("All 17 goals at a glance")
    if f.empty:
        st.info("No observations loaded.")
    else:
        fv = f[f["value_status"] != "not_available"]
        og = fv.groupby("goal").agg(series=("series_code", "nunique"), observations=("obs_id", "size"),
                                   first=("year", "min"), latest=("year", "max")).reindex(range(1, 18)).reset_index()
        og["name"] = og["goal"].map(lambda x: f"{x}. {config.GOALS[x]}")
        fig = px.bar(og, x="series", y="name", orientation="h", color="name", text="series",
                     color_discrete_map={f"{g}. {config.GOALS[g]}": c for g, c in GOAL_COLORS.items()},
                     hover_data={"observations": True, "first": True, "latest": True, "name": False})
        fig.update_traces(textposition="outside", textangle=0, cliponaxis=False)
        fig.update_layout(**LAYOUT, height=560, showlegend=False,
                          yaxis=dict(categoryorder="array", categoryarray=og["name"].tolist()[::-1], title=""),
                          xaxis_title="Data series with at least one India value")
        st.plotly_chart(fig, width="stretch")
        st.markdown("**How many series have data, by goal and year**")
        span = fv[fv["value"].notna()].groupby(["goal", "year"])["series_code"].nunique().unstack()
        span = span.reindex(index=range(1, 18), columns=range(int(fv["year"].min()), int(fv["year"].max()) + 1))
        fig = px.imshow(span.values, x=[str(c) for c in span.columns], y=[f"SDG {g}" for g in span.index],
                        color_continuous_scale=[[0, "#dbe9ed"], [1, ACCENT]], aspect="auto")
        fig.update_traces(xgap=1, ygap=1, hovertemplate="%{y}, %{x}: %{z} series<extra></extra>")
        fig.update_layout(**LAYOUT, height=470, xaxis=dict(title="Observation year", dtick=5),
                          coloraxis_colorbar=dict(title="Series", thickness=12))
        st.plotly_chart(fig, width="stretch")
        st.caption("Blank cells: no series has a value for that goal and year.")
        st.caption("Series filed under several goals count once under each. "
                   f"{tot.get('observations_before_2015', 0):,} observations predate the SDGs (before 2015) and are "
                   "kept as published; check series footnotes for breaks in definition.")

# ---------------------------------------------------------------- 5. data and downloads
with tabs[5]:
    st.subheader("Data and downloads")
    if f.empty:
        st.info("No observations loaded.")
    else:
        q = st.text_input("Search series descriptions", "")
        view = f[f["series_description"].str.contains(q, case=False, regex=False)] if q else f
        st.caption(f"{len(view):,} rows")
        st.dataframe(view.head(5000), hide_index=True, width="stretch")
        download(view, "sdg_india_observations_filtered.csv", "Download filtered observations (CSV)", "dl_f")
    c = st.columns(4)
    with c[0]:
        if (PROC / "observations.csv").exists():
            st.download_button("All observations", (PROC / "observations.csv").read_bytes(),
                               "sdg_india_observations_all.csv", "text/csv", key="dl_all")
    with c[1]:
        if not indicators.empty:
            download(indicators, "un_sdg_indicator_metadata.csv", "Indicator metadata", "dl_meta")
    with c[2]:
        if not scores.empty:
            download(scores, "niti_index_scores.csv", "NITI index scores", "dl_sc2")
    with c[3]:
        if not sources.empty:
            download(sources, "sources.csv", "Source register", "dl_src")

# ---------------------------------------------------------------- 6. sources and methods
with tabs[6]:
    st.subheader("Sources")
    if not sources.empty:
        s = sources.copy()
        s["status"] = s["status"].map(lambda x: json.loads(x).get("status", "") if isinstance(x, str) else "")
        st.dataframe(s[["source_id", "status", "kind", "name", "publisher", "url"]], hide_index=True, width="stretch",
                     column_config={"url": st.column_config.LinkColumn("Official URL")})
    if manifest.get("validation"):
        with st.expander("Validation report"):
            st.json(manifest["validation"])
    st.markdown("""
**Rules this project follows**
- Values are shown exactly as published. Missing values stay missing; nothing is interpolated or imputed.
- Values published as text (for example `<0.1` or `>95`) are kept as text and are not converted to numbers.
- Composite index scores (NITI Aayog) are stored and shown separately from raw indicator data.
- The observation year is kept separate from the publication or release date.
- Breakdowns (sex, age, location and others) are kept as published; "headline" means the total row the source provides.
- Each row records its source URL, raw file, SHA-256 checksum and retrieval time.
""")
