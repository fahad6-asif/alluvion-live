"""
General LIVE scan: "enter any US coordinates + an approximate fire date, and it
pulls the real satellite imagery and the real rainfall for that place/time and
runs the debris-flow model."

This is the generalized version of the Montecito hindcast. Everything is real,
pulled live from Earth Engine:
  - Burn scar (dNBR) from pre/post-fire Sentinel-2 (>=2016) or Landsat 8 (>=2014).
  - Terrain (SRTM slope) and soil (OpenLandMap -> USLE K proxy).
  - Rainfall (GPM IMERG) for a storm window (given, or auto-found peak after the fire).
  - USGS Staley-2017 M1 likelihood.

HONEST APPROXIMATIONS (surfaced in the API/UI):
  - No true watershed delineation for an arbitrary AOI (that needs pfdf/GDAL). We
    compute a GRIDDED / per-pixel debris-flow *susceptibility*: T is approximated
    by the local (~500 m neighborhood) fraction of steep-and-burned ground. It is
    a cell-based approximation of the per-basin USGS model, labeled as such.
  - I15 is an IMERG-derived ESTIMATE (areal-max x factor), not a gauge reading.
  - Soil is an OpenLandMap-derived K proxy for STATSGO KF (US-only).
  - It only "captures" an event where a fire AND a triggering storm actually
    occurred; elsewhere it honestly reports "no significant burn detected".
"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import ee_engine, model

# CONUS-ish envelope (soil proxy + these datasets are US-focused here)
CONUS = {"min_lat": 24.0, "max_lat": 50.0, "min_lon": -125.0, "max_lon": -66.0}
MODERATE_DNBR = ee_engine.MODERATE_DNBR
STEEP_DEG = ee_engine.STEEP_DEG
IMERG_TO_I15 = ee_engine.IMERG_TO_I15_FACTOR


def _aoi(lat, lon, radius_km):
    import ee
    d = radius_km / 111.0  # deg per km (approx)
    return ee.Geometry.Rectangle([lon - d, lat - d, lon + d, lat + d])


def _s2_nbr(aoi, start, end, max_cloud_prob=40):
    import ee
    s2 = ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(aoi).filterDate(start, end)
    cp = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(aoi).filterDate(start, end)
    joined = ee.Join.saveFirst("cp").apply(
        s2, cp, ee.Filter.equals(leftField="system:index", rightField="system:index"))

    def mask(img):
        img = ee.Image(img)
        prob = ee.Image(img.get("cp")).select("probability")
        return img.updateMask(prob.lt(max_cloud_prob)).divide(10000)

    col = ee.ImageCollection(joined).map(mask)
    return col.median().normalizedDifference(["B8", "B12"]).rename("nbr"), col.size()


def _l8_nbr(aoi, start, end):
    """Landsat 8 C02 L2 fallback for pre-2016 / imagery-sparse cases (MTBS uses Landsat)."""
    import ee

    def prep(img):
        qa = img.select("QA_PIXEL")
        cloud = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))  # cloud, cloud shadow
        sr = img.select(["SR_B5", "SR_B7"]).multiply(2.75e-5).add(-0.2)
        return sr.updateMask(cloud)

    col = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(aoi).filterDate(start, end).map(prep))
    comp = col.median()
    return comp.normalizedDifference(["SR_B5", "SR_B7"]).rename("nbr"), col.size()


def _nbr(aoi, start, end, sensor):
    return _s2_nbr(aoi, start, end) if sensor == "S2" else _l8_nbr(aoi, start, end)


def _pick_sensor(fire_date: datetime) -> str:
    # Sentinel-2 has reliable coverage from ~2016; use Landsat 8 for older fires.
    return "S2" if fire_date.year >= 2016 else "L8"


def _staley_image(T, F, S, i15):
    """Per-pixel Staley M1 probability as an EE image."""
    r = i15 * 0.25  # I15 (mm/hr) -> 15-min accumulation (mm)
    x = (T.multiply(model.M1_C_TERRAIN * r)
         .add(F.multiply(model.M1_C_FIRE * r))
         .add(S.multiply(model.M1_C_SOIL * r))
         .add(model.M1_INTERCEPT))
    return x.multiply(-1).exp().add(1).pow(-1).rename("p")


def _peak_storm(aoi, start, end):
    """Find the peak IMERG intensity in a window; return (peak_iso, series ±36h)."""
    import ee
    col = ee.ImageCollection("NASA/GPM_L3/IMERG_V07").filterDate(start, end).select("precipitation")
    if int(col.size().getInfo()) == 0:
        return None, []  # no rainfall data in this window (e.g., future / beyond IMERG latency)

    def tag(img):
        m = img.reduceRegion(ee.Reducer.max(), aoi, 11000).get("precipitation")
        return img.set("m", m)

    tagged = col.map(tag)
    peak_img = ee.Image(tagged.sort("m", False).first())
    peak_iso = peak_img.date().format("YYYY-MM-dd'T'HH:mm'Z'").getInfo()
    peak_dt = datetime.strptime(peak_iso, "%Y-%m-%dT%H:%MZ")

    win = col.filterDate((peak_dt - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M"),
                         (peak_dt + timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M"))

    def frame(img):
        v = img.reduceRegion(ee.Reducer.max(), aoi, 11000).get("precipitation")
        return ee.Feature(None, {"t": img.date().format("YYYY-MM-dd'T'HH:mm'Z'"), "mm": v})

    feats = win.map(frame).getInfo()["features"]
    series = []
    for f in feats:
        mm = float(f["properties"].get("mm") or 0.0)
        series.append({"t": f["properties"]["t"], "rain_mmhr": round(mm, 2),
                       "est_i15_mm_per_hr": round(mm * IMERG_TO_I15, 1)})
    return peak_iso, series


def burn_covariates(lat: float, lon: float, fire_date: str, radius_km: float = 6.0) -> dict:
    """
    Just the burn/terrain/soil part of a scan (no rainfall): detect the burn scar
    and return per-AOI T/F/S covariates + a dNBR tile + bbox. Reused by the
    WeatherNext forecast pipeline, which supplies its own (forecast) rainfall.
    """
    import ee
    ee_engine.initialize()
    fd = datetime.strptime(fire_date, "%Y-%m-%d")
    sensor = _pick_sensor(fd)
    aoi = _aoi(lat, lon, radius_km)
    pre = [(fd - timedelta(days=150)).strftime("%Y-%m-%d"), (fd - timedelta(days=15)).strftime("%Y-%m-%d")]
    post = [(fd + timedelta(days=15)).strftime("%Y-%m-%d"), (fd + timedelta(days=110)).strftime("%Y-%m-%d")]
    base = {"lat": lat, "lon": lon, "fire_date": fire_date, "sensor": sensor, "radius_km": radius_km}

    if fd.year < 2013:
        return {**base, "burn_detected": False,
                "message": "Burn detection needs Landsat 8 (2013+) / Sentinel-2 (2016+); date too early."}

    pre_nbr, pre_n = _nbr(aoi, pre[0], pre[1], sensor)
    post_nbr, post_n = _nbr(aoi, post[0], post[1], sensor)
    if int(pre_n.getInfo()) == 0 or int(post_n.getInfo()) == 0:
        return {**base, "burn_detected": False,
                "message": f"Not enough {sensor} imagery for this place/date."}

    dnbr = pre_nbr.subtract(post_nbr).multiply(1000).rename("dnbr")
    slope = ee.Terrain.slope(ee.Image("USGS/SRTMGL1_003")).rename("slope")
    soilK = ee_engine._soil_k(None).rename("S")
    steep_burned = slope.gte(STEEP_DEG).And(dnbr.gte(MODERATE_DNBR))
    burned = dnbr.gte(MODERATE_DNBR)

    stats = (steep_burned.rename("sb").addBands(burned.rename("burned"))
             .addBands(dnbr.updateMask(burned).rename("dnbr_b"))
             .addBands(soilK.updateMask(burned).rename("S_b"))
             .addBands(post_nbr.mask().rename("valid"))
             .reduceRegion(ee.Reducer.mean(), aoi, 60, maxPixels=1e9).getInfo())

    burned_fraction = float(stats.get("burned") or 0.0)
    valid_fraction = float(stats.get("valid") or 0.0)
    T = float(stats.get("sb") or 0.0)
    dnbr_b = float(stats.get("dnbr_b") or 0.0)
    S = float(stats.get("S_b") or 0.2)
    burn_detected = burned_fraction >= 0.03 and valid_fraction >= 0.2

    out = {**base, "burn_detected": burn_detected,
           "burned_fraction": round(burned_fraction, 3),
           "covariates": {"T": round(T, 3), "F": round(dnbr_b / 1000, 3), "S": round(S, 3),
                          "dnbr_mean_burned": round(dnbr_b)},
           "bbox": aoi.bounds().getInfo()["coordinates"][0],
           "dnbr_tile_url": _tile(dnbr, {"min": 0, "max": 800,
               "palette": ["1a9850", "d9ef8b", "fee08b", "fc8d59", "d73027"]})}
    if not burn_detected:
        out["message"] = f"No significant burn scar detected here ({round(burned_fraction*100)}% burned)."
    return out


def susceptibility_tile(lat: float, lon: float, fire_date: str, i15: float, radius_km: float = 6.0):
    """
    A debris-flow susceptibility tile (gridded per-pixel Staley at a given I15) for
    an arbitrary location. Shared by the Scan and Forecast tabs so both can toggle
    between the burn-severity and susceptibility map layers.
    """
    import ee
    ee_engine.initialize()
    fd = datetime.strptime(fire_date, "%Y-%m-%d")
    if fd.year < 2013:
        return None
    sensor = _pick_sensor(fd)
    aoi = _aoi(lat, lon, radius_km)
    pre = [(fd - timedelta(days=150)).strftime("%Y-%m-%d"), (fd - timedelta(days=15)).strftime("%Y-%m-%d")]
    post = [(fd + timedelta(days=15)).strftime("%Y-%m-%d"), (fd + timedelta(days=110)).strftime("%Y-%m-%d")]
    try:
        pre_nbr, _ = _nbr(aoi, pre[0], pre[1], sensor)
        post_nbr, _ = _nbr(aoi, post[0], post[1], sensor)
        dnbr = pre_nbr.subtract(post_nbr).multiply(1000).rename("dnbr")
        slope = ee.Terrain.slope(ee.Image("USGS/SRTMGL1_003")).rename("slope")
        soilK = ee_engine._soil_k(None).rename("S")
        steep_burned = slope.gte(STEEP_DEG).And(dnbr.gte(MODERATE_DNBR))
        burned = dnbr.gte(MODERATE_DNBR)
        T_local = steep_burned.reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.circle(500, "meters")).rename("T")
        susc = _staley_image(T_local, dnbr.divide(1000).rename("F"), soilK, i15).updateMask(burned)
        return _tile(susc, {"min": 0, "max": 1, "palette": ["2ca25f", "ffff00", "ff9900", "e31a1c"]})
    except Exception:
        return None


def scan(lat: float, lon: float, fire_date: str,
         storm_start: str = None, storm_end: str = None, radius_km: float = 6.0) -> dict:
    """Run the full real scan for an arbitrary US location + approximate fire date."""
    import ee
    ee_engine.initialize()

    fd = datetime.strptime(fire_date, "%Y-%m-%d")
    sensor = _pick_sensor(fd)
    aoi = _aoi(lat, lon, radius_km)
    in_conus = (CONUS["min_lat"] <= lat <= CONUS["max_lat"] and CONUS["min_lon"] <= lon <= CONUS["max_lon"])

    # pre/post-fire windows around the given fire date
    pre = [(fd - timedelta(days=150)).strftime("%Y-%m-%d"), (fd - timedelta(days=15)).strftime("%Y-%m-%d")]
    post = [(fd + timedelta(days=15)).strftime("%Y-%m-%d"), (fd + timedelta(days=110)).strftime("%Y-%m-%d")]

    base = {"lat": lat, "lon": lon, "fire_date": fire_date, "sensor": sensor,
            "radius_km": radius_km, "in_conus": in_conus,
            "prefire_window": pre, "postfire_window": post,
            "engine": "live-earthengine", "synthetic": False}

    # Coverage guard: optical imagery starts ~2013 (Landsat 8) / 2016 (Sentinel-2).
    if fd.year < 2013:
        return {**base, "burn_detected": False, "data_available": False,
                "message": ("Satellite burn detection here needs Landsat 8 (from 2013) "
                            "or Sentinel-2 (from 2016). This fire date is too early — "
                            "try an event from 2013 onward.")}

    pre_nbr, pre_n = _nbr(aoi, pre[0], pre[1], sensor)
    post_nbr, post_n = _nbr(aoi, post[0], post[1], sensor)
    n_pre = int(pre_n.getInfo()); n_post = int(post_n.getInfo())
    if n_pre == 0 or n_post == 0:
        return {**base, "burn_detected": False, "data_available": False,
                "n_prefire_scenes": n_pre, "n_postfire_scenes": n_post,
                "message": (f"Not enough {sensor} imagery for this place/date "
                            f"(pre={n_pre}, post={n_post} scenes). The date may be beyond "
                            f"current coverage, or too cloudy. Try a fire from 2016 onward.")}

    dnbr = pre_nbr.subtract(post_nbr).multiply(1000).rename("dnbr")

    slope = ee.Terrain.slope(ee.Image("USGS/SRTMGL1_003")).rename("slope")
    soilK = ee_engine._soil_k(None).rename("S")

    steep_burned = slope.gte(STEEP_DEG).And(dnbr.gte(MODERATE_DNBR))
    burned = dnbr.gte(MODERATE_DNBR)

    # AOI aggregate stats (one call)
    stats = (dnbr.rename("dnbr")
             .addBands(steep_burned.rename("sb"))
             .addBands(burned.rename("burned"))
             .addBands(dnbr.updateMask(burned).rename("dnbr_b"))
             .addBands(soilK.updateMask(burned).rename("S_b"))
             .addBands(post_nbr.mask().rename("valid"))
             .reduceRegion(ee.Reducer.mean(), aoi, 60, maxPixels=1e9).getInfo())

    burned_fraction = float(stats.get("burned") or 0.0)
    valid_fraction = float(stats.get("valid") or 0.0)
    T = float(stats.get("sb") or 0.0)
    dnbr_burned = float(stats.get("dnbr_b") or 0.0)
    F = dnbr_burned / 1000.0
    S = float(stats.get("S_b") or 0.2)

    burn_detected = burned_fraction >= 0.03 and valid_fraction >= 0.2

    result = {
        "lat": lat, "lon": lon, "fire_date": fire_date, "sensor": sensor,
        "radius_km": radius_km, "in_conus": in_conus,
        "prefire_window": pre, "postfire_window": post,
        "burn_detected": burn_detected,
        "data_available": True,
        "burned_fraction": round(burned_fraction, 3),
        "valid_fraction": round(valid_fraction, 2),
        "n_prefire_scenes": n_pre, "n_postfire_scenes": n_post,
        "covariates": {"T": round(T, 3), "F": round(F, 3), "S": round(S, 3),
                       "dnbr_mean_burned": round(dnbr_burned)},
        "engine": "live-earthengine",
        "synthetic": False,
        "notes": {
            "susceptibility": "Gridded per-pixel susceptibility (local steep-&-burned fraction), NOT true watersheds.",
            "i15": f"Estimated I15 = IMERG areal-max x {IMERG_TO_I15} (estimate, not a gauge reading).",
            "soil": "Soil K is an OpenLandMap proxy for STATSGO KF (US-only).",
        },
    }

    if not in_conus:
        result["warning_msg"] = "Outside the contiguous US — soil data is US-only, results unreliable."
    if not burn_detected:
        result["message"] = (
            f"No significant burn scar detected here in {post[0]}..{post[1]} "
            f"(burned {round(burned_fraction*100)}% of area, imagery valid {round(valid_fraction*100)}%). "
            f"Try coordinates over a known fire and a fire date within ~months of it."
        )
        # still return the dNBR tile so the user can see what the imagery shows
        result["dnbr_tile_url"] = _tile(dnbr, {"min": 0, "max": 800,
            "palette": ["1a9850", "d9ef8b", "fee08b", "fc8d59", "d73027"]})
        result["bbox"] = aoi.bounds().getInfo()["coordinates"][0]
        return result

    # --- real storm ---
    if storm_start and storm_end:
        peak_iso, series = _peak_storm(aoi, storm_start, storm_end)
    else:
        # auto-find the peak rain in the ~8 months after the fire (debris-flow season)
        peak_iso, series = _peak_storm(aoi, post[0],
                                       (fd + timedelta(days=240)).strftime("%Y-%m-%d"))
    peak = max(series, key=lambda s: s["est_i15_mm_per_hr"]) if series else None

    if peak is None:
        # burn detected, but no rainfall data in the search window (e.g., a very
        # recent fire beyond IMERG latency). Return the burn result without a storm.
        result["bbox"] = aoi.bounds().getInfo()["coordinates"][0]
        result["dnbr_tile_url"] = _tile(dnbr, {"min": 0, "max": 800,
            "palette": ["1a9850", "d9ef8b", "fee08b", "fc8d59", "d73027"]})
        result["storm_found"] = False
        result["storm_message"] = ("Burn scar detected, but no rainfall data was found in the "
                                    "search window (the fire may be too recent for GPM IMERG, "
                                    "or you can set an explicit storm date range).")
        return result

    peak_i15 = peak["est_i15_mm_per_hr"]

    # AOI probability at the storm peak, and the warning threshold
    cov = model.Covariates(T=T, F=F, S=S)
    aoi_prob_at_peak = round(model.likelihood(cov, peak_i15), 4)
    threshold_i15 = ee_engine._basin_threshold_i15({"T": T, "F": F, "S": S})

    # when did the real storm first cross the threshold?
    crossed = next((s for s in series if s["est_i15_mm_per_hr"] >= threshold_i15), None)

    # tiles: burn scar + susceptibility at the storm peak intensity
    T_local = steep_burned.reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.circle(500, "meters")).rename("T")
    F_local = dnbr.divide(1000).rename("F")
    susceptibility = _staley_image(T_local, F_local, soilK, peak_i15).updateMask(burned)

    result.update({
        "bbox": aoi.bounds().getInfo()["coordinates"][0],
        "dnbr_tile_url": _tile(dnbr, {"min": 0, "max": 800,
            "palette": ["1a9850", "d9ef8b", "fee08b", "fc8d59", "d73027"]}),
        "susceptibility_tile_url": _tile(susceptibility, {"min": 0, "max": 1,
            "palette": ["2ca25f", "ffff00", "ff9900", "e31a1c"]}),
        "storm_window": [storm_start or post[0], storm_end or (fd + timedelta(days=240)).strftime("%Y-%m-%d")],
        "storm_series": series,
        "storm_peak": peak,
        "peak_est_i15_mm_per_hr": peak_i15,
        "aoi_probability_at_peak": aoi_prob_at_peak,
        "warning_threshold_i15": threshold_i15,
        "threshold_crossed_at": crossed["t"] if crossed else None,
    })
    return result


def _tile(img, vis):
    try:
        return img.getMapId(vis)["tile_fetcher"].url_format
    except Exception:
        return None
