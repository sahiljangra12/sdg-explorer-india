# Paper: SDG Explorer India

**[Read the paper (PDF)](sdg_explorer_india.pdf)**: *SDG Explorer India: a verified open pipeline and interactive atlas of official Sustainable Development Goal data for India, from national series to 704 districts.*

Every number, table and figure in the paper is generated from this repository's data by `make_stats.py`; none is typed by hand.

To rebuild after the data change (from the repository root):

```bash
pip install scipy matplotlib
curl -LO https://raw.githubusercontent.com/pratapvardhan/NFHS-5/master/NFHS-5-Districts.csv   # independent NFHS-5 digitisation (CC BY 4.0)
python paper/make_stats.py . NFHS-5-Districts.csv
cd paper && latexmk -pdf sdg_explorer_india.tex
```

| File | What it is |
|---|---|
| `sdg_explorer_india.tex`, `references.bib` | LaTeX source and bibliography |
| `stats.tex` | Number macros used in the text (generated) |
| `tab_*.tex`, `fig_*.pdf` | Tables and figures (generated) |
| `numbers.json`, `district_associations.csv` | The same numbers in machine-readable form (generated) |
