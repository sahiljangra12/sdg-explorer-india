"""State and UT boundaries for the dashboard map (DataMeet India, CC BY 4.0).

The shapefile is downloaded once, simplified (about 1 km tolerance) to keep the dashboard
fast, matched to project geo_ids, and written as GeoJSON with attribution.
"""

from __future__ import annotations

import json

from . import config, geography
from .http import download, session

BASE = "https://raw.githubusercontent.com/datameet/maps/master/States/Admin2"
OUT = config.GEO / "india_states.geojson"
ATTRIBUTION = ("Boundaries: DataMeet India community, States/Admin2 (https://github.com/datameet/maps), "
               "CC BY 4.0. Simplified for display. Boundaries are illustrative and not an authoritative depiction "
               "of India's borders.")


def build(refresh: bool = False, tolerance: float = 0.01) -> dict:
    import shapefile  # pyshp
    from shapely.geometry import mapping, shape

    raw = config.RAW / "datameet_states"
    sess = session()
    for ext in ("shp", "dbf", "shx", "prj"):
        download(f"{BASE}.{ext}", raw / f"Admin2.{ext}", refresh=refresh, sess=sess)
    reader = shapefile.Reader(str(raw / "Admin2"))
    features, unmatched = [], []
    for sr in reader.shapeRecords():
        name = sr.record["ST_NM"]
        geo_id = geography.resolve(name)
        if geo_id is None:
            unmatched.append(name)
            continue
        geom = shape(sr.shape.__geo_interface__).simplify(tolerance, preserve_topology=True)
        features.append({"type": "Feature", "id": geo_id,
                         "properties": {"geo_id": geo_id, "geography": geography.name_of(geo_id), "source_name": name},
                         "geometry": _round(mapping(geom))})
    if unmatched:
        raise ValueError(f"Boundary names not matched to the geography registry: {unmatched}")
    fc = {"type": "FeatureCollection", "attribution": ATTRIBUTION, "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    return fc


def _round(geom: dict, nd: int = 4) -> dict:
    def r(c):
        return [round(c[0], nd), round(c[1], nd)] if isinstance(c[0], float | int) else [r(x) for x in c]
    return {"type": geom["type"], "coordinates": r(geom["coordinates"])}


def load() -> dict | None:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
