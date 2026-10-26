"""The NFHS-to-SDG mapping is applied consistently, with no invented indicator numbers."""

import pandas as pd
import pytest

from sdg_india.sources import nfhs


@pytest.mark.parametrize("raw, clean", [
    ("Children under 5 years who are stunted (height-for-age)18 (%)",
     "Children under 5 years who are stunted (height-for-age) (%)"),
    ("Women whose Body Mass Index (BMI) is below normal (BMI <18.5 kg/m 2)21 (%)",
     "Women whose Body Mass Index (BMI) is below normal (BMI <18.5 kg/m 2) (%)"),
    ("Births attended by skilled health personnel 10 (%)", "Births attended by skilled health personnel (%)"),
    ("Children age 5 years who attended pre-primary school during the school year 2019-20 (%)",
     "Children age 5 years who attended pre-primary school during the school year 2019-20 (%)"),
    ("Sex ratio at birth for children born in the last five years (females per 1,000 males)",
     "Sex ratio at birth for children born in the last five years (females per 1,000 males)"),
])
def test_footnote_numbers_removed(raw, clean):
    assert nfhs.clean_indicator_name(raw) == clean


def test_apply_map_codes_and_notes():
    df = pd.DataFrame({
        "series_code": ["NFHS_D073", "NFHS_D005", "NFHS_D094"],
        "footnotes": ["NFHS indicator 73: Children under 5 years who are stunted (height-for-age)18 (%) | "
                      "Relation to SDG: same (NIF 2.2.1)",
                      "NFHS indicator 5: Children under age 5 years whose birth was registered (%) | "
                      "Relation to SDG: related (target 16.9) | value in brackets",
                      "NFHS indicator 94: Elevated blood pressure (%) | Relation to SDG: related (NIF 3.8.4)"],
        "goal": [0, 0, 0], "target": ["", "", ""], "indicator_code": ["", "", ""],
        "indicator_codes_all": ["", "16.9.0", ""], "goals_all": ["", "", ""],
    })
    out = nfhs.apply_map(df)
    assert out["indicator_codes_all"].tolist() == ["2.2.1", "16.9", "3.8.4"]
    assert not out["indicator_codes_all"].str.endswith(".0").any()
    assert out["target"].tolist() == ["2.2", "16.9", "3.8"]
    assert out["goal"].tolist() == [2, 16, 3]
    assert out["footnotes"][0] == ("NFHS indicator 73: Children under 5 years who are stunted (height-for-age) (%) | "
                                   "Relation to SDG: same (NIF 2.2.1)")
    assert out["footnotes"][1].endswith("| value in brackets")


def test_every_target_matches_its_nif_code():
    for goal, target, relation, nif, _label, _unit in nfhs.SDG_MAP.values():
        assert relation in ("same", "related")
        assert target.split(".")[0] == str(goal)
        if nif:
            assert nif.rsplit(".", 1)[0] == target
