"""
Downstream EXPOSURE / IMPACT layer — turns hazard (does a debris flow occur?) into
RISK (does it hurt anything?).

Occurrence probability comes from the Staley model (unchanged). Risk = occurrence x
an exposure factor that is 0 when nothing is downstream and rises with people,
buildings, roads and rivers in the debris-flow runout zone. A red basin above empty
wilderness has HIGH occurrence but ~0 risk; a red basin above a town has both.

DANGER, NOT JUST A HEADCOUNT: the exposure factor is NOT a flat count of everything
inside the runout zone. Something sitting right at the base of the steep burned
source (where debris actually piles up) is in far more danger than something the
same "downstream" but 6 km away at the edge of the search radius, even though both
sit on gentle slope. So every layer is weighted by a proximity/danger curve
`exp(-distance_from_the_burn_source / decay)` BEFORE it is summed into a category
factor — a person 200 m from the source counts close to fully, a person 6 km out is
discounted to ~13%. The RAW (unweighted) counts are still reported in `metrics` /
category `detail` text for honesty about what's actually out there; only the factor
that drives `risk = occurrence x factor` uses the danger-weighted totals. See
`_danger_weight_image` / `_weight_features`.

Data (all via Google Earth Engine + Google Maps Platform):
  - People      : WorldPop GP 100m (US-covered).
  - Built-up    : JRC GHSL built surface (US-covered proxy for buildings, since
                  Google Open Buildings V3 does NOT cover the US).
  - Roads       : US Census TIGER/2016/Roads.
  - Rivers      : WWF HydroSHEDS free-flowing rivers.
  - Facilities  : Google Places API (Nearby Search) — OPTIONAL, needs a Maps API
                  key in GOOGLE_MAPS_API_KEY; gated gracefully if absent.

Runout/exposure zone: debris deposits on the gentle ground BELOW the steep burned
source. We approximate it as the AOI's gentle-slope area (slope < 12 deg) — the
valley floor / outwash plain where settlements sit. It is an approximation of true
flow routing (labeled as such), not a hydraulic runout model.
"""

from __future__ import annotations

import math
import os
import threading

from . import ee_engine

RUNOUT_MAX_SLOPE_DEG = 12          # gentle valley floor where debris deposits & people live
# Danger decays with distance from the AOI center (the fire/basin location the
# frontend passes in). decay = a fraction of the search radius, so a wider scan
# still discounts its own far edge the same relative amount.
DANGER_DECAY_FRACTION = 0.5
_CACHE: dict = {}
_LOCK = threading.Lock()


def _aoi(lat, lon, radius_km):
    import ee
    d = radius_km / 111.0
    return ee.Geometry.Rectangle([lon - d, lat - d, lon + d, lat + d])


def _sat(x, scale):
    """Saturating exposure curve 1 - e^(-x/scale): rises smoothly, rarely hits 1.0,
    so real values spread out instead of everything pinning at 100%."""
    return round(1.0 - math.exp(-max(0.0, x) / scale), 3)


def _danger_weight_image(lat, lon, decay_m):
    """Per-pixel danger weight in [0,1]: exp(-distance_from(lat,lon)/decay_m).
    Close to the burn/hazard source -> ~1 (full danger); far from it -> discounted.
    Distance is a flat-earth approximation (fine at the few-km AOI scale used here).
    """
    import ee
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat))
    dy = ee.Image.pixelLonLat().select("latitude").subtract(lat).multiply(m_per_deg_lat)
    dx = ee.Image.pixelLonLat().select("longitude").subtract(lon).multiply(m_per_deg_lon)
    dist_m = dx.pow(2).add(dy.pow(2)).sqrt()
    return dist_m.divide(decay_m).multiply(-1).exp().rename("danger_w")


def _weight_features(fc, lat, lon, decay_m, length_weighted):
    """Tag each feature in a FeatureCollection with a proximity danger weight
    exp(-distance_to(lat,lon)/decay_m). If length_weighted, also sets 'wlen' =
    geometry length x weight (for roads); otherwise just 'w' (for river reaches,
    counted by presence not length)."""
    import ee
    center = ee.Geometry.Point([lon, lat])

    def tag(f):
        d = f.geometry().distance(center, 10)
        w = d.divide(decay_m).multiply(-1).exp()
        f = f.set("w", w)
        if length_weighted:
            f = f.set("wlen", ee.Number(f.geometry().length(10)).multiply(w))
        return f

    return fc.map(tag)


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _risk_categories(people_raw, people_w, buildings, road_km_raw, road_km_w,
                      rivers_n_raw, rivers_w, cropland_km2_raw, cropland_km2_w,
                      facilities_n, facilities_w, facilities_available):
    """
    Separate exposure factors [0,1] per thing-at-stake, each multiplied by occurrence
    to give that category's risk. Uses saturating curves calibrated so a real town
    lands around 0.4-0.7 (not pinned at 1.0), giving a believable spread across
    categories instead of a wall of identical ~100% numbers.

    The factor is driven by the DANGER-WEIGHTED total (`*_w` args) — people/roads/
    rivers/farmland discounted by how far they sit from the burn/hazard source, per
    `_danger_weight_image` — not the raw headcount. A 6 km search radius that
    happens to sweep in a distant, unrelated town no longer reads as equally
    "exposed" as a town sitting right at the base of the burned slope. The `*_raw`
    args are for the human-readable `detail` text only, so the report still states
    the real numbers.

    Scales (the danger-weighted value at which a category reaches ~63% exposure):
      people 25,000 · roads 500 km · rivers 3.5 reaches · farmland 4 km^2.
    Waterways stay first-class (a flow into a river is a serious sediment/ecology/
    water event even with no people nearby).
    """
    people_property = _sat(people_w, 25000)
    infrastructure = _sat(road_km_w, 500)
    if facilities_available:
        infrastructure = round(min(1.0, 0.7 * infrastructure + 0.3 * _sat(facilities_w, 4)), 3)
    waterways = _sat(rivers_w, 3.5) if rivers_n_raw >= 1 else 0.0
    farmland = _sat(cropland_km2_w, 4.0)

    return {
        "people_property": {"label": "People & property", "factor": people_property,
                            "detail": f"{people_raw:,} people, ~{buildings:,} buildings downstream "
                                      f"({people_w:,.0f} risk-weighted for proximity to the burn source)"},
        "infrastructure": {"label": "Roads & facilities", "factor": infrastructure,
                           "detail": f"{road_km_raw} km of roads ({road_km_w:.1f} km risk-weighted)" +
                                     (f", {facilities_n} critical facilities" if facilities_available else "")},
        "waterways": {"label": "Waterways & ecosystem", "factor": waterways,
                      "detail": (f"{rivers_n_raw} river reach{'es' if rivers_n_raw != 1 else ''} in the runout path "
                                 f"({rivers_w:.1f} risk-weighted for proximity) — mud can choke flow, harm aquatic "
                                 "life, and foul water supply")
                                if rivers_n_raw else "no rivers downstream"},
        "farmland": {"label": "Farmland & crops", "factor": farmland,
                     "detail": (f"{cropland_km2_raw} km^2 of cultivated land downstream ({cropland_km2_w:.2f} km^2 "
                                "risk-weighted) — burial by debris/sediment can destroy a season's crops")
                                if cropland_km2_raw > 0.05 else "no cultivated farmland downstream"},
    }


def _satellite_thumb(aoi):
    """A real true-color Sentinel-2 PNG of the area (getThumbURL) — Gemini's vision input."""
    import ee
    try:
        s2 = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(aoi)
              .filterDate("2023-01-01", "2024-08-01")
              .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 15)).median().divide(10000))
        return s2.getThumbURL({"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.3,
                               "region": aoi, "dimensions": 512, "format": "png"})
    except Exception:
        return None


def _places_facilities(lat, lon, radius_m=6000):
    """Google Places Nearby Search for critical facilities. OPTIONAL (needs key)."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        return None
    try:
        import urllib.parse
        import urllib.request
        import json
        out = []
        for typ in ("hospital", "school", "fire_station"):
            q = urllib.parse.urlencode({"location": f"{lat},{lon}", "radius": radius_m,
                                        "type": typ, "key": key})
            url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?{q}"
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
            for p in data.get("results", [])[:8]:
                loc = p["geometry"]["location"]
                out.append({"name": p.get("name"), "type": typ,
                            "lat": loc["lat"], "lon": loc["lng"]})
        return out
    except Exception:
        return None


def exposure(lat: float, lon: float, radius_km: float = 6.0, force: bool = False) -> dict:
    """Compute downstream exposure metrics + highlight layers for an AOI."""
    import ee
    ee_engine.initialize()
    key = (round(lat, 3), round(lon, 3), radius_km)
    with _LOCK:
        if not force and key in _CACHE:
            return _CACHE[key]

    aoi = _aoi(lat, lon, radius_km)
    slope = ee.Terrain.slope(ee.Image("USGS/SRTMGL1_003"))
    zone = slope.lt(RUNOUT_MAX_SLOPE_DEG)   # gentle runout/deposition zone

    decay_m = radius_km * 1000.0 * DANGER_DECAY_FRACTION
    danger_w = _danger_weight_image(lat, lon, decay_m)   # 1 near the source, decaying outward

    # --- people (WorldPop) in the runout zone: raw count + danger-weighted ---
    pop = (ee.ImageCollection("WorldPop/GP/100m/pop")
           .filterDate("2020-01-01", "2021-01-01").filterBounds(aoi).mosaic().select("population"))
    pop_zone = pop.updateMask(zone)
    people = pop_zone.reduceRegion(ee.Reducer.sum(), aoi, 100, maxPixels=1e9).get("population")
    people_w = pop_zone.multiply(danger_w).reduceRegion(ee.Reducer.sum(), aoi, 100, maxPixels=1e9).get("population")

    # --- built-up surface (GHSL) in the runout zone ---
    built = ee.Image("JRC/GHSL/P2023A/GHS_BUILT_S/2020").select("built_surface")
    built_m2 = built.updateMask(zone).reduceRegion(ee.Reducer.sum(), aoi, 100, maxPixels=1e9).get("built_surface")

    # --- roads (TIGER): raw total length + danger-weighted length in AOI ---
    roads = ee.FeatureCollection("TIGER/2016/Roads").filterBounds(aoi)
    road_len_m = roads.geometry().length(maxError=10)
    roads_w = _weight_features(roads, lat, lon, decay_m, length_weighted=True)
    road_len_w_m = roads_w.aggregate_sum("wlen")

    # --- rivers (HydroSHEDS): raw count + danger-weighted count intersecting AOI ---
    rivers = ee.FeatureCollection("WWF/HydroSHEDS/v1/FreeFlowingRivers").filterBounds(aoi)
    rivers_w_fc = _weight_features(rivers, lat, lon, decay_m, length_weighted=False)
    rivers_w_sum = rivers_w_fc.aggregate_sum("w")

    # --- farmland (USDA Cropland Data Layer) in the runout zone: raw + danger-weighted ---
    cdl = ee.ImageCollection("USDA/NASS/CDL").filter(ee.Filter.date("2020-01-01", "2021-01-01")).first().select("cultivated")
    crop_zone = cdl.eq(2).updateMask(zone)
    crop_m2 = crop_zone.multiply(ee.Image.pixelArea()).reduceRegion(
        ee.Reducer.sum(), aoi, 30, maxPixels=1e9).get("cultivated")
    crop_w_m2 = crop_zone.multiply(danger_w).multiply(ee.Image.pixelArea()).reduceRegion(
        ee.Reducer.sum(), aoi, 30, maxPixels=1e9).get("cultivated")

    # one round-trip for the scalar metrics
    stats = ee.Dictionary({
        "people": people, "people_w": people_w, "built_m2": built_m2,
        "road_m": road_len_m, "road_w_m": road_len_w_m,
        "rivers_n": rivers.size(), "rivers_w": rivers_w_sum,
        "crop_m2": crop_m2, "crop_w_m2": crop_w_m2,
    }).getInfo()

    people_n = int(stats.get("people") or 0)
    people_w_n = float(stats.get("people_w") or 0.0)
    built_m2_n = float(stats.get("built_m2") or 0.0)
    road_km = round(float(stats.get("road_m") or 0.0) / 1000.0, 1)
    road_km_w = float(stats.get("road_w_m") or 0.0) / 1000.0
    rivers_n = int(stats.get("rivers_n") or 0)
    rivers_w_n = float(stats.get("rivers_w") or 0.0)
    cropland_km2 = round(float(stats.get("crop_m2") or 0.0) / 1e6, 2)
    cropland_km2_w = float(stats.get("crop_w_m2") or 0.0) / 1e6
    buildings_est = int(built_m2_n / 150.0)   # ~150 m^2 average footprint

    facilities = _places_facilities(lat, lon, int(radius_km * 1000))
    facilities_n = len(facilities) if facilities else 0
    facilities_w_n = 0.0
    if facilities:
        facilities_w_n = sum(math.exp(-_haversine_km(lat, lon, f["lat"], f["lon"]) * 1000.0 / decay_m)
                             for f in facilities)

    categories = _risk_categories(people_n, people_w_n, buildings_est, road_km, road_km_w,
                                  rivers_n, rivers_w_n, cropland_km2, cropland_km2_w,
                                  facilities_n, facilities_w_n, facilities is not None)
    factor = round(max(c["factor"] for c in categories.values()), 3)   # worst-threatened category

    # --- a real satellite thumbnail (PNG) of the area, for Gemini's vision input ---
    satellite_thumb_url = _satellite_thumb(aoi)

    # --- highlight layers for the map ---
    def tile(img, vis):
        try:
            return img.getMapId(vis)["tile_fetcher"].url_format
        except Exception:
            return None

    pop_hi = pop.updateMask(zone).updateMask(pop.gt(1))
    people_tile = tile(pop_hi, {"min": 0, "max": 40, "palette": ["cfe8ff", "6baed6", "2171b5", "08306b"]})
    roads_img = ee.Image().byte().paint(roads, 1).updateMask(ee.Image().byte().paint(roads, 1))
    roads_tile = tile(roads_img, {"palette": ["ffd400"]})
    rivers_geojson = None
    try:
        rivers_geojson = rivers.limit(50).getInfo()
    except Exception:
        rivers_geojson = None

    result = {
        "lat": lat, "lon": lon, "radius_km": radius_km,
        "metrics": {
            "people": people_n,
            "people_danger_weighted": round(people_w_n),
            "buildings_est": buildings_est,
            "built_m2": int(built_m2_n),
            "road_km": road_km,
            "road_km_danger_weighted": round(road_km_w, 1),
            "rivers_n": rivers_n,
            "rivers_danger_weighted": round(rivers_w_n, 1),
            "cropland_km2": cropland_km2,
            "cropland_km2_danger_weighted": round(cropland_km2_w, 2),
            "facilities_n": facilities_n,
        },
        "exposure_factor": factor,          # = worst-threatened category (for the headline)
        "risk_categories": categories,
        "satellite_thumb_url": satellite_thumb_url,
        "aoi_bbox": [round(lon - radius_km / 111.0, 4), round(lat - radius_km / 111.0, 4),
                     round(lon + radius_km / 111.0, 4), round(lat + radius_km / 111.0, 4)],
        "facilities": facilities,           # None if no Maps key
        "facilities_available": facilities is not None,
        "people_tile_url": people_tile,
        "roads_tile_url": roads_tile,
        "rivers_geojson": rivers_geojson,
        "notes": {
            "occurrence_vs_risk": "Occurrence = debris-flow probability (unchanged). "
                                  "Risk = occurrence x exposure factor; 0 when nothing is downstream.",
            "danger_weighting": "The exposure factor is driven by DANGER-weighted totals, not raw headcounts: "
                                f"everything in the runout zone is discounted by exp(-distance from the burn "
                                f"source / {decay_m/1000:.1f} km), so something right at the base of the burned "
                                "slope counts far more than the same thing at the edge of the search radius. "
                                "Raw counts are still shown alongside the weighted ones.",
            "runout_zone": f"Exposure counted in the gentle runout zone (slope < {RUNOUT_MAX_SLOPE_DEG} deg) — "
                           "an approximation of the debris deposition area, not a hydraulic flow model.",
            "buildings": "Built-up from JRC GHSL (Google Open Buildings V3 does not cover the US).",
            "facilities": "Critical facilities via Google Places API (needs GOOGLE_MAPS_API_KEY)."
                          if facilities is None else "Critical facilities via Google Places API.",
        },
    }
    with _LOCK:
        _CACHE[key] = result
    return result
