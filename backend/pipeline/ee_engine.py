"""
LIVE Google Earth Engine hindcast engine.

Runs the debris-flow early-warning pipeline BLIND against real archived data, as
if it were operating the week of the disaster. A hard time cutoff means it only
ever touches data that existed before the event (a temporal holdout — the honest
way to validate a warning system).

What is REAL here (pulled live from Earth Engine at request time):
  - Burn severity (dNBR): differenced pre/post-fire Sentinel-2 L1C composites,
    cloud-masked. NBR = (B8 - B12)/(B8 + B12); dNBR = pre - post (burned > 0).
  - Terrain: SRTM DEM -> slope in degrees (steep = >= 23 deg, the USGS threshold).
  - Rainfall: GPM IMERG half-hourly precipitation over the AOI, replayed at its
    real UTC timestamps (the storm builds exactly as it did on 9 Jan 2018).
  - Likelihood: the published USGS Staley-2017 M1 equation (pipeline/model.py),
    applied to real per-basin covariates.

Two honestly-labeled approximations (EE lacks a clean source for each):
  - SOIL (S): OpenLandMap clay/sand/organic -> USLE K-factor (Wischmeier). A real,
    spatially-varying erodibility proxy; the operational tool uses STATSGO KF.
  - BASINS: drainage bands across the burned front (simplified catchments). The
    operational tool delineates true catchments from the DEM via pfdf. ALL hazard
    inputs computed *within* each basin are real EE data.

I15 note: IMERG is a 30-minute areal mean at ~11 km, which smooths localized peak
15-minute point intensity. We convert to an ESTIMATED I15 with a stated factor and
label it as an estimate, never a measurement (same honesty as the WeatherNext
caveat). The real 9 Jan gauge peak was ~78-105 mm/hr.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from . import model

# ---------------------------------------------------------------- EE lifecycle
_INIT_LOCK = threading.Lock()
_INITIALIZED = False


def available() -> bool:
    """True if earthengine-api imports AND we can initialize (stored creds)."""
    try:
        return initialize()
    except Exception:
        return False


def initialize() -> bool:
    """
    Authenticate to Earth Engine. Tries, in order:

    1. A SERVICE ACCOUNT supplied as JSON in EE_SERVICE_ACCOUNT_JSON (the whole
       key file pasted into one env var — how Render/Vercel store secrets). This
       is the deploy path: the key never expires and survives every restart, so
       the app never silently falls back. The account email and Cloud project are
       read from inside the JSON, so no other env var is needed.
    2. GOOGLE_APPLICATION_CREDENTIALS pointing at a service-account key *file*
       (for anyone who prefers a file on disk), with EE_SERVICE_ACCOUNT giving
       the account email.
    3. Plain ee.Initialize() using interactive `earthengine authenticate`
       credentials — the local-dev path, unchanged.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return True
    with _INIT_LOCK:
        if _INITIALIZED:
            return True
        import os
        import ee

        # (1) Service account as inline JSON — the durable deploy path.
        raw = os.environ.get("EE_SERVICE_ACCOUNT_JSON")
        if raw:
            import json
            info = json.loads(raw)
            email = info.get("client_email")
            project = os.environ.get("EE_PROJECT") or info.get("project_id")
            if not email:
                raise RuntimeError(
                    "EE_SERVICE_ACCOUNT_JSON is set but has no 'client_email'. "
                    "Paste the FULL service-account key JSON."
                )
            creds = ee.ServiceAccountCredentials(email, key_data=raw)
            ee.Initialize(creds, project=project) if project else ee.Initialize(creds)
            _INITIALIZED = True
            return True

        # (2) Service account as a key file on disk.
        key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        email = os.environ.get("EE_SERVICE_ACCOUNT")
        if key_file and email and os.path.exists(key_file):
            project = os.environ.get("EE_PROJECT")
            creds = ee.ServiceAccountCredentials(email, key_file)
            ee.Initialize(creds, project=project) if project else ee.Initialize(creds)
            _INITIALIZED = True
            return True

        # (3) Interactive local credentials (`earthengine authenticate`).
        try:
            ee.Initialize()
        except Exception:
            proj = os.environ.get("EE_PROJECT")
            ee.Initialize(project=proj) if proj else ee.Initialize()
        _INITIALIZED = True
        return True


# ---------------------------------------------------------------- preset config
@dataclass(frozen=True)
class LivePreset:
    fire_id: str
    name: str
    bbox: List[float]            # [minLon, minLat, maxLon, maxLat]
    prefire: List[str]           # [start, end] pre-fire imagery window
    postfire: List[str]          # [start, end] post-fire window (before cutoff)
    cutoff: str                  # blind cutoff date (pipeline sees nothing after)
    storm_window: List[str]      # [start, end] to replay real precip over
    # named creeks along the burned front, W->E, with outlet longitude
    creeks: List[Dict]


THOMAS = LivePreset(
    fire_id="thomas_fire",
    name="Thomas Fire (2017) above Montecito",
    bbox=[-119.70, 34.40, -119.55, 34.48],
    prefire=["2017-10-01", "2017-11-30"],     # before ignition (4 Dec 2017)
    postfire=["2017-12-13", "2018-01-06"],    # scar visible, BEFORE 9 Jan event
    cutoff="2018-01-06",
    storm_window=["2018-01-08", "2018-01-10"],
    creeks=[
        {"name": "Montecito Creek", "lon": -119.655},
        {"name": "San Ysidro Creek", "lon": -119.635},
        {"name": "Buena Vista Creek", "lon": -119.620},
        {"name": "Romero Creek", "lon": -119.603},
        {"name": "Toro Canyon Creek", "lon": -119.586},
    ],
)

# Source-basin extent on the burned front (steep upper catchments feed the creeks)
FRONT_LAT_BASE = 34.442   # base of the mountain front (creek outlets)
FRONT_LAT_RIDGE = 34.480  # ridge / headwaters
MODERATE_DNBR = 270       # USGS moderate-or-higher burn threshold
STEEP_DEG = 23            # USGS steep threshold

# IMERG (30-min, ~11 km areal mean) -> estimated peak 15-min POINT intensity.
# Combines a temporal-peak factor (~1.5, 30-min -> 15-min burst) and an
# areal-to-point factor (~2, 11 km cell -> local point). STATED ESTIMATE.
# Kept conservative (3.0, not 5.0) so probabilities are not pinned near 100% —
# the model saturates at extreme intensities, and over-inflating I15 made every
# result read as ~100%. Real localized gauge peaks can still exceed this estimate.
IMERG_TO_I15_FACTOR = 3.0


# ---------------------------------------------------------------- EE geometry
def _aoi(preset: LivePreset):
    import ee
    return ee.Geometry.Rectangle(preset.bbox)


def _basin_bands(preset: LivePreset):
    """Simplified per-creek catchments: longitude bands across the burned front."""
    import ee
    lons = [c["lon"] for c in preset.creeks]
    # band edges midway between adjacent creeks
    edges = []
    left = preset.bbox[0] + 0.004
    for i in range(len(lons)):
        right = (lons[i] + lons[i + 1]) / 2 if i + 1 < len(lons) else preset.bbox[2] - 0.004
        edges.append((left, right))
        left = right
    feats = []
    for c, (x0, x1) in zip(preset.creeks, edges):
        poly = ee.Geometry.Rectangle([x0, FRONT_LAT_BASE, x1, FRONT_LAT_RIDGE])
        feats.append(ee.Feature(poly, {"name": c["name"], "outlet_lon": c["lon"]}))
    return ee.FeatureCollection(feats)


# ---------------------------------------------------------------- REAL layers
def _s2_composite(preset, start, end, max_cloud_prob=40):
    """
    Cloud-masked median Sentinel-2 L1C reflectance composite, using the
    s2cloudless cloud-probability collection (QA60 is too weak for this sparse
    winter imagery and either leaves gaps or lets contamination flip dNBR
    negative). NBR and true-color RGB are both derived from this.
    """
    import ee
    aoi = _aoi(preset)
    s2 = ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(aoi).filterDate(start, end)
    cp = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(aoi).filterDate(start, end)
    joined = ee.Join.saveFirst("cp").apply(
        s2, cp, ee.Filter.equals(leftField="system:index", rightField="system:index")
    )

    def mask(img):
        img = ee.Image(img)
        prob = ee.Image(img.get("cp")).select("probability")
        return img.updateMask(prob.lt(max_cloud_prob)).divide(10000)

    return ee.ImageCollection(joined).map(mask).median()


def _s2_nbr(preset, start, end, max_cloud_prob=40):
    """Cloud-masked median NBR = (B8 - B12)/(B8 + B12)."""
    return _s2_composite(preset, start, end, max_cloud_prob).normalizedDifference(["B8", "B12"]).rename("nbr")


def _dnbr(preset):
    """REAL dNBR (burned > 0) from pre/post-fire Sentinel-2, honoring the cutoff."""
    pre = _s2_nbr(preset, *preset.prefire)
    post = _s2_nbr(preset, *preset.postfire)
    return pre.subtract(post).multiply(1000).rename("dnbr")


def _rgb_tile(preset, start, end):
    """True-color Sentinel-2 tile URL for the pre/post-fire imagery walkthrough."""
    try:
        comp = _s2_composite(preset, start, end)
        m = comp.getMapId({"bands": ["B4", "B3", "B2"], "min": 0.0, "max": 0.3})
        return m["tile_fetcher"].url_format
    except Exception:
        return None


def _slope_deg(preset):
    import ee
    return ee.Terrain.slope(ee.Image("USGS/SRTMGL1_003")).rename("slope")


def _soil_k(preset):
    """
    REAL soil erodibility K (USLE / Wischmeier) from OpenLandMap texture.
    K ~ f(silt, sand, organic matter). Spatially varying; a labeled proxy for
    the STATSGO KF-factor the operational tool uses.
    """
    import ee
    clay = ee.Image("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02").select("b10")
    sand = ee.Image("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02").select("b10")
    om = ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02").select("b10").multiply(0.1)
    silt = ee.Image(100).subtract(clay).subtract(sand).max(0)
    # Wischmeier textural factor M = (silt + very-fine-sand) * (100 - clay), with
    # very-fine-sand approximated by silt. Scaled so typical values land in the
    # realistic KF band (~0.1-0.4) and reduced slightly by organic matter.
    M = silt.multiply(2).multiply(ee.Image(100).subtract(clay))
    K = M.multiply(5.5e-5).subtract(om.multiply(0.02)).rename("K").clamp(0.10, 0.42)
    return K


# ---------------------------------------------------------------- covariates
def _covariates_per_basin(preset) -> List[Dict]:
    """Compute REAL T/F/S per basin band in one reduceRegions call each."""
    import ee
    aoi = _aoi(preset)
    bands = _basin_bands(preset)
    dnbr = _dnbr(preset)
    slope = _slope_deg(preset)
    K = _soil_k(preset)

    steep_burned = slope.gte(STEEP_DEG).And(dnbr.gte(MODERATE_DNBR)).rename("T")
    stack = steep_burned.addBands(dnbr.rename("Fdnbr")).addBands(K.rename("S"))

    reduced = stack.reduceRegions(
        collection=bands, reducer=ee.Reducer.mean(), scale=60
    ).getInfo()

    out = []
    for f in reduced["features"]:
        p = f["properties"]
        T = float(p.get("T") or 0.0)          # fraction steep & burned
        dnbr_mean = float(p.get("Fdnbr") or 0.0)
        S = float(p.get("S") or 0.2)
        out.append(
            {
                "name": p["name"],
                "outlet_lon": p["outlet_lon"],
                "geometry": f["geometry"],
                "T": round(T, 3),
                "dnbr": round(dnbr_mean),
                "F": round(dnbr_mean / 1000.0, 3),
                "S": round(S, 3),
            }
        )
    return out


def dnbr_tile_url(preset) -> Optional[str]:
    """A Leaflet XYZ tile URL for the REAL burn-severity layer (for the map)."""
    try:
        import ee
        dnbr = _dnbr(preset)
        vis = {"min": 0, "max": 800,
               "palette": ["1a9850", "d9ef8b", "fee08b", "fc8d59", "d73027"]}
        m = dnbr.getMapId(vis)
        return m["tile_fetcher"].url_format
    except Exception:
        return None


# ---------------------------------------------------------------- storm replay
def storm_series(preset) -> List[Dict]:
    """REAL half-hourly rainfall intensity over the AOI, replayed at true UTC times."""
    import ee
    aoi = _aoi(preset)
    col = (
        ee.ImageCollection("NASA/GPM_L3/IMERG_V07")
        .filterDate(*preset.storm_window)
        .select("precipitation")
    )

    def frame(img):
        stats = img.reduceRegion(ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
                                 aoi, 11000)
        return ee.Feature(None, {
            "t": img.date().format("YYYY-MM-dd'T'HH:mm'Z'"),
            "mean_mmhr": stats.get("precipitation_mean"),
            "max_mmhr": stats.get("precipitation_max"),
        })

    feats = col.map(frame).getInfo()["features"]
    series = []
    for f in feats:
        p = f["properties"]
        areal = float(p.get("max_mmhr") or 0.0)   # use areal max as the intensity signal
        series.append({
            "t": p["t"],
            "rain_mmhr": round(areal, 2),
            "est_i15_mm_per_hr": round(areal * IMERG_TO_I15_FACTOR, 1),
        })
    return series


# ---------------------------------------------------------------- assembly + cache
_CACHE: Dict[str, dict] = {}
_CACHE_LOCK = threading.Lock()


def _basin_threshold_i15(cov: Dict, target_p: float = 0.5) -> float:
    """The estimated I15 at which this basin's probability crosses target_p.

    Inverts the Staley M1 logistic for the basin's real covariates -> the storm
    intensity that trips a warning (USGS-style intensity-duration threshold).
    """
    import math
    c = model.Covariates(T=cov["T"], F=cov["F"], S=cov["S"])
    denom = (model.M1_C_TERRAIN * c.T + model.M1_C_FIRE * c.F + model.M1_C_SOIL * c.S)
    if denom <= 1e-9:
        return float("inf")
    logit = math.log(target_p / (1 - target_p))
    accum = (logit - model.M1_INTERCEPT) / denom           # 15-min accumulation (mm)
    return round(accum / (model.MINUTES_PER_I15_WINDOW / 60.0), 1)  # -> mm/hr


def run_replay(preset: LivePreset = THOMAS, force: bool = False) -> dict:
    """
    Full blind hindcast: detect the fire + terrain + soil, pull the real storm,
    and compute per-basin probability at every timestep + the warning each basin
    would have issued (first time its estimated I15 crossed its 50% threshold).
    Cached per fire_id (EE calls are the slow part).
    """
    initialize()
    with _CACHE_LOCK:
        if not force and preset.fire_id in _CACHE:
            return _CACHE[preset.fire_id]

    covs = _covariates_per_basin(preset)
    series = storm_series(preset)
    tile = dnbr_tile_url(preset)
    prefire_rgb = _rgb_tile(preset, *preset.prefire)
    postfire_rgb = _rgb_tile(preset, *preset.postfire)

    # per-basin static info + warning threshold
    basins = []
    for cov in covs:
        thr = _basin_threshold_i15(cov)
        basins.append({**{k: cov[k] for k in ("name", "outlet_lon", "T", "dnbr", "F", "S")},
                       "threshold_i15_mm_per_hr": thr,
                       "geometry": cov["geometry"]})

    # time-stepped probabilities + first-warning events
    timeline = []
    warnings: Dict[str, dict] = {}
    for step in series:
        i15 = step["est_i15_mm_per_hr"]
        probs = {}
        for cov, b in zip(covs, basins):
            p = model.likelihood(model.Covariates(T=cov["T"], F=cov["F"], S=cov["S"]), i15)
            probs[b["name"]] = round(p, 4)
            if b["name"] not in warnings and i15 >= b["threshold_i15_mm_per_hr"]:
                warnings[b["name"]] = {"name": b["name"], "t": step["t"],
                                       "i15": i15, "probability": round(p, 4)}
        timeline.append({"t": step["t"], "rain_mmhr": step["rain_mmhr"],
                         "est_i15_mm_per_hr": i15, "prob": probs})

    peak = max(series, key=lambda s: s["est_i15_mm_per_hr"]) if series else None
    result = {
        "fire_id": preset.fire_id,
        "name": preset.name,
        "bbox": preset.bbox,
        "blind_cutoff": preset.cutoff,
        "engine": "live-earthengine",
        "synthetic": False,
        "prefire_window": preset.prefire,
        "postfire_window": preset.postfire,
        "dnbr_tile_url": tile,
        "prefire_rgb_tile_url": prefire_rgb,
        "postfire_rgb_tile_url": postfire_rgb,
        "flow_onset_utc": "2018-01-09T11:30Z",   # ~3:30 AM PST, when the flows struck
        "basins": basins,
        "timeline": timeline,
        "warnings": sorted(warnings.values(), key=lambda w: w["t"]),
        "peak": peak,
        "imerg_to_i15_factor": IMERG_TO_I15_FACTOR,
        "notes": {
            "blind": f"Pipeline used only imagery/precip on or before the storm; "
                     f"post-fire imagery window ends {preset.cutoff}.",
            "soil": "S is a real OpenLandMap-derived USLE K erodibility proxy (STATSGO KF operationally).",
            "basins": "Basins are simplified drainage bands across the burned front; hazard inputs within them are real EE data.",
            "i15": f"Estimated I15 = IMERG areal-max x {IMERG_TO_I15_FACTOR} (stated estimate, not a gauge measurement).",
        },
    }
    with _CACHE_LOCK:
        _CACHE[preset.fire_id] = result
    return result
