# Methods and data rules

## What counts as an observation

An observation is one published value of one data series, for one geography, one reference period and one breakdown (for example: share of population below the international poverty line, India, 2019, both sexes). Every observation keeps:

| Field | Meaning |
|---|---|
| `obs_id` | Stable identifier: a hash of source, series, geography, period and breakdown |
| `goal`, `target`, `indicator_code` | SDG goal, target and global indicator code as published |
| `series_code`, `series_description` | The data series (an indicator can have several series) |
| `geo_id`, `geography`, `geo_level` | Project geography identifier, name and level (national, state, union territory, district) |
| `year`, `time_period` | Start year of the reference period, and the period as published (e.g. `2019-2021`) |
| `value`, `value_raw` | The number, and the value exactly as published |
| `unit`, `unit_multiplier`, `nature` | Unit, scale and nature code (C = country data, E = estimated, M = modelled, and so on) |
| `dimensions`, `headline` | Breakdown (sex, age, location ...) as published, and whether this is the series' total row |
| `lower_bound`, `upper_bound`, `base_period` | Uncertainty bounds and base period where published |
| `original_source`, `footnotes` | The survey or administrative source named by the publisher, and its footnotes |
| `release` | The publisher's release identifier, distinct from the observation year |
| `source_url`, `raw_file`, `raw_sha256`, `retrieved_at` | Exact request URL, raw file, its SHA-256 and retrieval time |

## Rules

1. **Nothing is invented or filled in.** Missing years stay missing; charts break their lines at gaps instead of bridging them.
2. **Values are kept as published.** Values published as text (`<0.1`, `>95`, `N`) are kept in `value_raw`, and `value` is left empty. They are never turned into numbers.
3. **Composite index scores are separate.** NITI Aayog's SDG India Index scores are normalised, weighted composites. They live in `index_scores.csv` and a separate dashboard panel, and validation fails if one appears in the observation table.
4. **Observation year is not publication date.** `year`/`time_period` describe the reference period; `release` and the source register describe publication.
5. **Breakdowns are preserved.** "Headline" marks the total row a source provides (both sexes, all areas ...). If a series has no total row, no row is marked headline and the user chooses a breakdown.
6. **Pre-2015 values are kept** when the publisher includes them. Check series footnotes for breaks in definition before comparing across years.
7. **Different sources are not merged.** A UN series and a MoSPI series for the same indicator stay separate, because definitions, data sources and revisions can differ.

## MoSPI NIF report: how tables are read

The MoSPI NIF Progress Report 2025 has one small table per national indicator in its Data Snapshot section (report PDF pages 80–153). The PDF's text layer is read with Poppler's `pdftotext -layout`, which keeps the column positions. The rules:

- A table is parsed only if its header ("Year" plus value columns) is on one line, every data row starts with a period (`2015-16`, `2019`, `2019 to 2024`) and has exactly one value per column.
- Tables are skipped and listed in `not_parsed.csv` (never guessed) if:
  - the header spans several lines
  - a period repeats, which means a hidden grouping column such as quarter
  - column names repeat
  - any line in the table column cannot be explained
- Indian digit grouping (`1,09,085`) and stray spaces inside numbers (`277 .0865`) are normalised. Footnote markers (`66.6614*`) are recorded with their footnote. `-` and `NA` are kept as the publisher's not-available markers. Values such as `(-)73.8` and `Yes` are kept as text.
- The unit is taken from the table header when given (`Value (in lakhs)`); otherwise it is stated in the indicator name.
- MoSPI codes are national NIF codes. They follow SDG target numbering but are not the same indicators as the UN global codes.
- **Independent verification.** After parsing, every table row is checked with a different method: pdfplumber word positions on the printed page. The period and its values must appear left to right on the same line. A row that cannot be confirmed is dropped, unless it has been confirmed on the rendered page image and listed in the code.
- **Tables the text parser skips** (multi-line headers, hidden quarter columns) are read a second way where possible: from the table's drawn gridlines with pdfplumber. This is done only for 23 tables whose column labels were reviewed on the page image (`GRID_REVIEW` in `sdg_india/sources/mospi.py`). Every row must also be confirmed in Poppler's text layout. On the tables both parsers can read, they agree on all 773 shared rows.
- If the PDF is missing, damaged, or Poppler is not installed, the verified extract in `data/reference/` is used instead of re-parsing with a different engine.

## NFHS district fact sheets: how they are read

Each NFHS-5 District Fact Sheet is a two- or three-page PDF with about 104 numbered indicators and two columns: NFHS-5 (2019-21) and NFHS-4 (2015-16). Districts formed after 2015-16 have only the NFHS-5 column; their NFHS-4 values are absent, not empty.

- **Which indicators.** 34 indicators with a clear SDG counterpart are kept (`SDG_MAP` in `sdg_india/sources/nfhs.py`). Each is marked either "same" (the same measure as a national NIF indicator, for example stunting = NIF 2.2.1) or "related" (relevant to the SDG target, not the official indicator).
- **District and State.** The district name is taken from the cover page and must match the sentence "In <district>, information was gathered ..." later in the same document. The State comes from the title line.
- **Indicators are matched by name.** The standard name of each number is the name printed most often against it across all 704 sheets. Each sheet's rows are then matched to those names. Two official sheets (Mahisagar, Wardha) skip a number in their list, so their printed numbers are shifted; matching by name corrects this, and the correction is recorded.
- **Values.** Values in brackets are based on 25–49 unweighted cases; they are kept, with a note. `*` (fewer than 25 cases) and `na` are kept as "not available". Values whose numbers were split across lines out of column order are left out and listed, never guessed.
- **Cross-check.** The extract was compared with an independent digitisation of the same fact sheets (pratapvardhan/NFHS-5): 20,409 of 20,413 shared values are identical, and the 4 differences are a column shift in that copy.
- **District identifiers** are `<State id>.<district slug>`, for example `IN.UP.lucknow`. District boundaries are not mapped.
- **No aggregation.** State or national values are never computed from district values; survey weights differ.

## District grouping: NITI Aayog MPI and Aspirational Districts

These two sources describe districts; they are not SDG indicator observations. They are stored in
`data/processed/district_context.csv` and used only to group and filter districts on the website.

- **MPI 2023 district tables.** For each district: headcount ratio H (% of people multidimensionally
  poor), intensity A and MPI, for NFHS-4 and NFHS-5, copied as published. Hidden text (an earlier
  copy of a neighbouring State's table drawn under the printed one) is removed by dropping glyphs that a
  later-drawn filled shape covers. A row is loaded only if MPI = H × A within 0.0015. Rows are matched to
  NFHS districts by name within the State, then by a reviewed alias list; districts that were split or
  merged after NFHS-5 are left unmatched and listed, never given another district's value.
- **Poverty level** on the website: the 704 districts are split into five equal-sized groups by the
  NFHS-5 headcount ratio (cuts at the 20th, 40th, 60th and 80th percentiles of districts). The group
  ranges are shown next to each choice.
- **Indicators that are part of the MPI.** The MPI is built from NFHS-5 data, including nutrition,
  maternal health, cooking fuel, sanitation, drinking water and electricity. NFHS indicators that measure
  one of these are marked, because their link with the headcount ratio is partly built in.
- **Aspirational Districts.** NITI Aayog's list of 112. Four districts created after NFHS-5 are not linked.
- **Statistics shown.** Relationships are described with Spearman's rank correlation (needs at least 10
  districts) and groups with medians and box plots across districts. These describe districts, not people,
  are unweighted by population, and show association only.

## Completeness checks on download

- UN SDG API: every page from 1 to `totalPages` must be present, all pages must report the same `totalElements`, and the number of records must equal it. Otherwise the build stops.
- Refreshes are atomic: new files are downloaded into a staging folder, checked, and only then swapped in.
- Downloads are retried with exponential back-off on connection errors and HTTP 429/5xx responses.

## Validation (every build)

Errors stop the build and keep the previous build in place. Errors include: empty provenance fields, duplicate observations, goal codes outside 1–17, implausible years, unknown geographies, composite scores among observations, and a missing value with no published raw value. Warnings are reported for review: values published as text, and percentages outside 0–100.

## Geography

`data/processed/geographies.csv` lists India, the 28 States, the 8 Union Territories, and two former Union Territories (Dadra and Nagar Haveli; Daman and Diu, merged in 2020). Jammu and Kashmir was a state until 31 October 2019; values before then cover the former state, which included Ladakh. Andhra Pradesh values before June 2014 include Telangana. Identifiers such as `IN.UP` are project identifiers, not ISO 3166-2 codes.

Map boundaries come from the DataMeet India community (States/Admin2, CC BY 4.0), simplified for display. They are illustrative and not an authoritative depiction of India's borders.
