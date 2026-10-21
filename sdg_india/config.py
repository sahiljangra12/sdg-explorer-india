"""Paths, SDG goal names and the register of official sources."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
REFERENCE = DATA / "reference"
GEO = DATA / "geo"

UN_API_BASE = "https://unstats.un.org/sdgapi/v1/sdg"
INDIA_M49 = 356
UN_PAGE_SIZE = 1000
USER_AGENT = "SDG-Explorer-India/2.0 (research use; source provenance retained)"

GOALS = {
    1: "No Poverty",
    2: "Zero Hunger",
    3: "Good Health and Well-being",
    4: "Quality Education",
    5: "Gender Equality",
    6: "Clean Water and Sanitation",
    7: "Affordable and Clean Energy",
    8: "Decent Work and Economic Growth",
    9: "Industry, Innovation and Infrastructure",
    10: "Reduced Inequalities",
    11: "Sustainable Cities and Communities",
    12: "Responsible Consumption and Production",
    13: "Climate Action",
    14: "Life Below Water",
    15: "Life on Land",
    16: "Peace, Justice and Strong Institutions",
    17: "Partnerships for the Goals",
}

# Every source the pipeline knows about. `kind` says how its numbers may be used:
#   observation      raw indicator values (time series)
#   composite_index  published index scores; never mixed with raw observations
#   district_context attributes of districts used to group and filter them (poverty level, programme
#                    membership); kept in their own table, never mixed with indicator observations
#   reference        metadata or boundaries only
SOURCES = [
    {
        "source_id": "UN_SDG_API",
        "name": "UN Global SDG Indicators Database (UNSD SDG API v1)",
        "publisher": "United Nations Statistics Division",
        "kind": "observation",
        "url": "https://unstats.un.org/sdgs/dataportal/database",
        "access_url": f"{UN_API_BASE}/Indicator/Data?areaCode={INDIA_M49}",
        "documentation": "https://unstats.un.org/sdgapi/swagger/",
        "geography": "National (India)",
    },
    {
        "source_id": "UN_SDG_METADATA",
        "name": "UN SDG goal, target, indicator and series list (UNSD SDG API v1)",
        "publisher": "United Nations Statistics Division",
        "kind": "reference",
        "url": f"{UN_API_BASE}/Goal/List?includechildren=true",
        "access_url": f"{UN_API_BASE}/Series/List?allreleases=false",
        "documentation": "https://unstats.un.org/sdgapi/swagger/",
        "geography": "",
    },
    {
        "source_id": "MOSPI_NIF_2025",
        "name": "Sustainable Development Goals: National Indicator Framework Progress Report, 2025",
        "publisher": "Ministry of Statistics and Programme Implementation (MoSPI), Government of India",
        "kind": "observation",
        "url": "https://www.mospi.gov.in/sites/default/files/publication_reports/"
               "Sustainable%20Development%20Goals%20National%20Indicator%20Framework%20Progress%20Report%2C%202025.pdf",
        "access_url": "",
        "documentation": "https://mospi.gov.in/sdg",
        "geography": "National (India)",
    },
    {
        "source_id": "NITI_SDGII_2023_24",
        "name": "SDG India Index 2023-24",
        "publisher": "NITI Aayog, Government of India",
        "kind": "composite_index",
        "url": "https://www.niti.gov.in/sites/default/files/2024-07/SDG_India_Index_2023-24.pdf",
        "access_url": "",
        "documentation": "https://sdgindiaindex.niti.gov.in/",
        "geography": "States and Union Territories",
    },
    {
        "source_id": "NFHS5_DISTRICTS",
        "name": "National Family Health Survey (NFHS-5) District Fact Sheets, 2019-21 (with NFHS-4, 2015-16)",
        "publisher": "Ministry of Health and Family Welfare / International Institute for Population Sciences (IIPS)",
        "kind": "observation",
        "url": "http://rchiips.org/nfhs/districtfactsheet_NFHS-5.shtml",
        "access_url": "https://github.com/SaiSiddhardhaKalla/NFHS/tree/main/pdfs",
        "documentation": "http://rchiips.org/nfhs/",
        "geography": "Districts (704)",
    },
    {
        "source_id": "NITI_MPI_2023",
        "name": "National Multidimensional Poverty Index: A Progress Review 2023 (district tables)",
        "publisher": "NITI Aayog, Government of India (with OPHI and UNDP)",
        "kind": "district_context",
        "url": "https://www.niti.gov.in/sites/default/files/2023-08/India-National-Multidimentional-Poverty-Index-2023.pdf",
        "access_url": "",
        "documentation": "https://www.niti.gov.in/whats-new/national-multidimentional-poverty-index-2023",
        "geography": "Districts (NFHS-4 and NFHS-5)",
    },
    {
        "source_id": "NITI_ASPIRATIONAL",
        "name": "List of 112 Aspirational Districts",
        "publisher": "NITI Aayog, Government of India",
        "kind": "district_context",
        "url": "https://www.niti.gov.in/sites/default/files/2023-07/List-of-112-Aspirational-Districts%20%281%29.pdf",
        "access_url": "",
        "documentation": "https://www.niti.gov.in/aspirational-districts-programme",
        "geography": "Districts (112)",
    },
    {
        "source_id": "DATAMEET_STATES",
        "name": "India state boundaries (States/Admin2)",
        "publisher": "DataMeet India community (CC BY 4.0)",
        "kind": "reference",
        "url": "https://github.com/datameet/maps/tree/master/States",
        "access_url": "https://raw.githubusercontent.com/datameet/maps/master/States/Admin2.shp",
        "documentation": "https://projects.datameet.org/maps/states/",
        "geography": "States and Union Territories",
    },
]
SOURCE_BY_ID = {s["source_id"]: s for s in SOURCES}
