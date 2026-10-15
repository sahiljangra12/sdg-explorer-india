"""Readable labels for SDG codes, units and breakdowns (shared by the dashboard and the website)."""

from __future__ import annotations

import json

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
