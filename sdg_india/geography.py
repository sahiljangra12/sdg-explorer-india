"""Registry of India's geographies and a resolver for the many spellings used in official reports.

Identifiers (``geo_id``) are project identifiers built from common two-letter abbreviations,
for example ``IN.UP`` for Uttar Pradesh. They are not ISO 3166-2 codes.
"""

from __future__ import annotations

import re

import pandas as pd

# geo_id, name, level, valid_from, valid_to, note
_REGISTRY = [
    ("IN", "India", "national", None, None, ""),
    # States (28)
    ("IN.AP", "Andhra Pradesh", "state", None, None,
     "Telangana was carved out on 2 June 2014; earlier values cover the combined state."),
    ("IN.AR", "Arunachal Pradesh", "state", None, None, ""),
    ("IN.AS", "Assam", "state", None, None, ""),
    ("IN.BR", "Bihar", "state", None, None, ""),
    ("IN.CG", "Chhattisgarh", "state", None, None, ""),
    ("IN.GA", "Goa", "state", None, None, ""),
    ("IN.GJ", "Gujarat", "state", None, None, ""),
    ("IN.HR", "Haryana", "state", None, None, ""),
    ("IN.HP", "Himachal Pradesh", "state", None, None, ""),
    ("IN.JH", "Jharkhand", "state", None, None, ""),
    ("IN.KA", "Karnataka", "state", None, None, ""),
    ("IN.KL", "Kerala", "state", None, None, ""),
    ("IN.MP", "Madhya Pradesh", "state", None, None, ""),
    ("IN.MH", "Maharashtra", "state", None, None, ""),
    ("IN.MN", "Manipur", "state", None, None, ""),
    ("IN.ML", "Meghalaya", "state", None, None, ""),
    ("IN.MZ", "Mizoram", "state", None, None, ""),
    ("IN.NL", "Nagaland", "state", None, None, ""),
    ("IN.OD", "Odisha", "state", None, None, ""),
    ("IN.PB", "Punjab", "state", None, None, ""),
    ("IN.RJ", "Rajasthan", "state", None, None, ""),
    ("IN.SK", "Sikkim", "state", None, None, ""),
    ("IN.TN", "Tamil Nadu", "state", None, None, ""),
    ("IN.TS", "Telangana", "state", 2014, None, "Formed on 2 June 2014."),
    ("IN.TR", "Tripura", "state", None, None, ""),
    ("IN.UP", "Uttar Pradesh", "state", None, None, ""),
    ("IN.UK", "Uttarakhand", "state", None, None, ""),
    ("IN.WB", "West Bengal", "state", None, None, ""),
    # Union Territories (8)
    ("IN.AN", "Andaman and Nicobar Islands", "union_territory", None, None, ""),
    ("IN.CH", "Chandigarh", "union_territory", None, None, ""),
    ("IN.DH", "Dadra and Nagar Haveli and Daman and Diu", "union_territory", 2020, None,
     "Formed on 26 January 2020 by merging two Union Territories."),
    ("IN.DL", "Delhi", "union_territory", None, None, "National Capital Territory of Delhi."),
    ("IN.JK", "Jammu and Kashmir", "union_territory", None, None,
     "A state until 31 October 2019, when it was reorganised into the Union Territories of Jammu and Kashmir "
     "and Ladakh. Earlier values cover the former state."),
    ("IN.LA", "Ladakh", "union_territory", 2019, None, "Formed on 31 October 2019."),
    ("IN.LD", "Lakshadweep", "union_territory", None, None, ""),
    ("IN.PY", "Puducherry", "union_territory", None, None, ""),
    # Former Union Territories, kept so that historical values are not lost or misassigned
    ("IN.DN", "Dadra and Nagar Haveli", "former_union_territory", None, 2019, "Merged into IN.DH in 2020."),
    ("IN.DD", "Daman and Diu", "former_union_territory", None, 2019, "Merged into IN.DH in 2020."),
]

_ALIASES = {
    "andaman nicobar": "IN.AN",
    "andaman and nicobar": "IN.AN",
    "a and n islands": "IN.AN",
    "an islands": "IN.AN",
    "nct of delhi": "IN.DL",
    "delhi nct": "IN.DL",
    "national capital territory of delhi": "IN.DL",
    "orissa": "IN.OD",
    "pondicherry": "IN.PY",
    "uttaranchal": "IN.UK",
    "chattisgarh": "IN.CG",
    "chhatisgarh": "IN.CG",
    "j and k": "IN.JK",
    "jammu kashmir": "IN.JK",
    "dnh and dd": "IN.DH",
    "dadra nagar haveli and daman diu": "IN.DH",
    "dadra and nagar haveli daman and diu": "IN.DH",
    "the dadra and nagar haveli and daman and diu": "IN.DH",
    "dadra nagar haveli": "IN.DN",
    "daman diu": "IN.DD",
    "all india": "IN",
    "india total": "IN",
    "total india": "IN",
}


def registry() -> pd.DataFrame:
    return pd.DataFrame(_REGISTRY, columns=["geo_id", "geography", "geo_level", "valid_from", "valid_to", "note"])


def _key(name: str) -> str:
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"[^a-z ]+", " ", s)
    s = re.sub(r"\b(the|ut|u t|state of)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_LOOKUP = {_key(name): geo_id for geo_id, name, *_ in _REGISTRY}
_LOOKUP.update({_key(k): v for k, v in _ALIASES.items()})
_NAMES = {geo_id: name for geo_id, name, *_ in _REGISTRY}
_LEVELS = {geo_id: level for geo_id, _, level, *_ in _REGISTRY}


def resolve(name: str) -> str | None:
    """Return the geo_id for a geography name as written in a source, or None if unknown."""
    return _LOOKUP.get(_key(name))


def name_of(geo_id: str) -> str:
    return _NAMES[geo_id]


def level_of(geo_id: str) -> str:
    return _LEVELS[geo_id]


CURRENT_STATES_AND_UTS = [g for g, _, level, *_ in _REGISTRY if level in ("state", "union_territory")]
