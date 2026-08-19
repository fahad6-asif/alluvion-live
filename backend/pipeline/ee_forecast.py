"""
Forward-looking debris-flow outlook from a weather FORECAST model (not rain that
already fell). Pipeline: detect the burn scar from satellite (real) -> pull a
forecast-model precipitation series for the location -> convert to an estimated
I15 -> run the USGS Staley model -> warnings.

Two selectable forecast sources (build decision: support both):
  - "cfsv2"  : NOAA CFSv2 (NOAA/CFSV2/FOR6H_HARMONIZED). PUBLIC, no access gate,
               covers 2011->present — so it works for HISTORICAL scenarios like
               Montecito 2018/2019. Coarse (~22 km, 6-hour average), so magnitudes
               are heavily smoothed and the I15 estimate is rough. This is the
               right tool for pre-WeatherNext dates.
  - "weathernext" : Google WeatherNext (higher-res, newer) — but GATED (needs an
               access request) and RECENT-only, so it cannot do 2018/2019. Use for
               recent/current fires once access is granted.

Honest caveats (surfaced in the UI, badged EXPERIMENTAL):
  - Both give a coarse gridded total; the peak 15-minute I15 is an ASSUMPTION-based
    disaggregation, not a measurement.
  - WeatherNext terms: data "not intended, validated, or approved for real world use."
  - The forecast is model output, not what actually fell (that's the hindcast/scan).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import ee_engine, ee_scan, model

# ---- CFSv2 (public, historical) ----
CFSV2_ASSET = "NOAA/CFSV2/FOR6H_HARMONIZED"
CFSV2_BAND = "Precipitation_rate_surface_6_Hour_Average"   # kg/m^2/s == mm/s
# 6-hour-average rate -> estimated peak 15-min intensity. Large factor because a
# 6-hour, ~22 km average massively smooths convective peaks. STATED ESTIMATE.
CFSV2_TO_I15_FACTOR = 6.0

# ---- WeatherNext (gated, recent) ----
WEATHERNEXT_ASSETS = [
    "projects/gcp-public-data-weathernext/assets/weathernext_2_0_0",
    "projects/gcp-public-data-weathernext/assets/126478713_1_0",
]
WN_6HR_MEAN_TO_I15_PEAK = 4.0


# ----------------------------------------------------------------- WeatherNext gate
def _wn_load():
    import ee
    for aid in WEATHERNEXT_ASSETS:
        try:
            col = ee.ImageCollection(aid)
            col.limit(1).size().getInfo()
            return col, aid
        except Exception:
            continue
    return None, None


def weathernext_available() -> bool:
    try:
        ee_engine.initialize()
        col, _ = _wn_load()
        return col is not None
    except Exception:
        return False


def status() -> dict:
    """Availability of each forecast source (CFSv2 is always available)."""
    wn = weathernext_available()
    return {
        "sources": {
            "cfsv2": {"available": True, "label": "NOAA CFSv2 (public, 2011–now)",
                      "note": "Coarse ~22 km 6-hourly forecast; works for historical dates (2018/2019)."},
            "weathernext": {"available": wn, "label": "Google WeatherNext (recent, higher-res)",
                            "note": ("Ready." if wn else
                                     "Needs Earth Engine access — open the WeatherNext dataset in the "
                                     "Data Catalog and click 'Request access'. Recent dates only.")},
        },
        "default": "cfsv2",
        "asset_weathernext": WEATHERNEXT_ASSETS[0],
    }


# ----------------------------------------------------------------- source series
def _cfsv2_series(lat, lon, start, end):
    """Auto-find the peak forecast storm in [start,end]; return a 6-hourly series."""
    import ee
    pt = ee.Geometry.Point([lon, lat])
    col = ee.ImageCollection(CFSV2_ASSET).filterDate(start, end).select(CFSV2_BAND)
    if int(col.size().getInfo()) == 0:
        return None, []

    def tag(img):
        m = img.reduceRegion(ee.Reducer.mean(), pt, 22000).get(CFSV2_BAND)
        return img.set("m", m)

    peak_img = ee.Image(col.map(tag).sort("m", False).first())
    peak_iso = peak_img.date().format("YYYY-MM-dd'T'HH:mm'Z'").getInfo()
    pdt = datetime.strptime(peak_iso, "%Y-%m-%dT%H:%MZ")
    win = col.filterDate((pdt - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
                         (pdt + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"))

    def frame(img):
        v = img.reduceRegion(ee.Reducer.mean(), pt, 22000).get(CFSV2_BAND)
        return ee.Feature(None, {"t": img.date().format("YYYY-MM-dd'T'HH:mm'Z'"), "rate": v})

    feats = win.map(frame).getInfo()["features"]
    series = []
    for f in feats:
        rate = float(f["properties"].get("rate") or 0.0)   # mm/s
        mmhr = rate * 3600.0
        series.append({"t": f["properties"]["t"], "precip_mmhr": round(mmhr, 2),
                       "est_i15_mm_per_hr": round(mmhr * CFSV2_TO_I15_FACTOR, 1)})
    return peak_iso, series


def _weathernext_series(lat, lon):
    """Latest WeatherNext forecast run -> 6-hourly precip series (needs access)."""
    import ee
    col, _ = _wn_load()
    if col is None:
        return None, []
    pt = ee.Geometry.Point([lon, lat])
    sample = ee.Image(col.limit(1).first()).getInfo()
    bands = [b["id"] for b in sample.get("bands", [])]
    props = list(sample.get("properties", {}).keys())
    pband = "total_precipitation_6hr" if "total_precipitation_6hr" in bands else \
        next((b for b in bands if "precip" in b.lower()), None)
    if not pband:
        return None, []
    init_prop = next((k for k in ("forecast_reference_time", "creation_time", "init_time") if k in props), None)
    run = (col.filter(ee.Filter.eq(init_prop, col.aggregate_max(init_prop))) if init_prop
           else col.sort("system:time_start", False).limit(60))
    run = run.sort("system:time_start")

    # the run's initialization/issue time (when this forecast was "taken")
    issue_iso = None
    try:
        issue_iso = ee.Image(run.first()).date().format("YYYY-MM-dd'T'HH:mm'Z'").getInfo()
    except Exception:
        issue_iso = None

    def frame(img):
        v = img.select(pband).reduceRegion(ee.Reducer.mean(), pt, 28000).get(pband)
        return ee.Feature(None, {"t": img.date().format("YYYY-MM-dd'T'HH:mm'Z'"), "p6h": v})

    feats = run.map(frame).getInfo()["features"]
    series = []
    for f in feats:
        p6h = f["properties"].get("p6h")
        if p6h is None:
            continue
        total_mm = float(p6h) * 1000.0   # meters -> mm (assumption; verify on access)
        mean_mmhr = total_mm / 6.0
        series.append({"t": f["properties"]["t"], "precip_mmhr": round(mean_mmhr, 2),
                       "est_i15_mm_per_hr": round(mean_mmhr * WN_6HR_MEAN_TO_I15_PEAK, 1)})
    return issue_iso, series


# ----------------------------------------------------------------- main
def forecast(lat: float, lon: float, fire_date: str, source: str = "cfsv2",
             radius_km: float = 6.0, storm_start: str = None, storm_end: str = None) -> dict:
    ee_engine.initialize()
    source = (source or "cfsv2").lower()

    # 1) real burn/terrain/soil covariates
    burn = ee_scan.burn_covariates(lat, lon, fire_date, radius_km)
    base = {"lat": lat, "lon": lon, "fire_date": fire_date, "source": source,
            "experimental": True, "engine": f"{source}-forecast"}
    if not burn.get("burn_detected"):
        return {**base, "available": True, "burn_detected": False,
                "message": burn.get("message", "No burn scar detected here."),
                "dnbr_tile_url": burn.get("dnbr_tile_url"), "bbox": burn.get("bbox")}

    cov = burn["covariates"]
    covm = model.Covariates(T=cov["T"], F=cov["F"], S=cov["S"])
    threshold = ee_engine._basin_threshold_i15({"T": cov["T"], "F": cov["F"], "S": cov["S"]})

    # 2) forecast precip series from the chosen source
    fd = datetime.strptime(fire_date, "%Y-%m-%d")
    wn_issue_iso = None
    if source == "weathernext":
        if not weathernext_available():
            return {**base, "available": False,
                    "message": "WeatherNext access not granted for this account yet.",
                    **status()}
        wn_issue_iso, series = _weathernext_series(lat, lon)
        src_label = "Google WeatherNext"
        disagg = f"Estimated I15 = (6-hour forecast total / 6 h) x {WN_6HR_MEAN_TO_I15_PEAK}. Assumption, not a measurement."
    else:
        win = ([storm_start, storm_end] if storm_start and storm_end else
               [(fd + timedelta(days=15)).strftime("%Y-%m-%d"),
                (fd + timedelta(days=240)).strftime("%Y-%m-%d")])
        _, series = _cfsv2_series(lat, lon, win[0], win[1])
        src_label = "NOAA CFSv2"
        disagg = f"Estimated I15 = CFSv2 6-hour-avg rate x {CFSV2_TO_I15_FACTOR}. Coarse model; rough estimate, not a measurement."

    if not series:
        return {**base, "available": True, "burn_detected": True, "covariates": cov,
                "bbox": burn["bbox"], "dnbr_tile_url": burn["dnbr_tile_url"],
                "message": f"{src_label} returned no precipitation for this place/date window."}

    # 3) likelihood per step + first warning + peak
    timeline, warning = [], None
    for s in series:
        i15 = s["est_i15_mm_per_hr"]
        prob = round(model.likelihood(covm, i15), 4)
        step = {**s, "probability": prob}
        timeline.append(step)
        if warning is None and i15 >= threshold:
            warning = {"t": step["t"], "est_i15": i15, "probability": prob}
    peak = max(timeline, key=lambda s: s["est_i15_mm_per_hr"]) if timeline else None

    # --- forecast issue time / lead ---
    def _ms(iso):
        return datetime.strptime(iso, "%Y-%m-%dT%H:%MZ")

    issued = None          # when the forecast run was initialized (if the source records it)
    lead_days = None       # issue -> predicted peak, in days
    issue_note = None
    if source == "weathernext":
        issued = wn_issue_iso   # captured from the run below (may be None)
        if issued and peak:
            lead_days = round((_ms(peak["t"]) - _ms(issued)).total_seconds() / 86400.0, 1)
    else:
        issue_note = ("CFSv2 in Earth Engine doesn't record when each forecast was issued, "
                      "so a true 'issued N days ahead' lead isn't available for this source. "
                      "WeatherNext (recent fires) does provide it.")

    # Honest, source-independent lead derived from the forecast content itself:
    # how far AHEAD of the predicted peak the forecast first crossed the threshold.
    warn_lead_hours = None
    if warning and peak:
        warn_lead_hours = round((_ms(peak["t"]) - _ms(warning["t"])).total_seconds() / 3600.0, 1)

    # susceptibility map layer at the peak forecast intensity (so the Forecast tab
    # can toggle burn-severity <-> susceptibility, like the Scan tab)
    susc_tile = None
    if peak and peak["est_i15_mm_per_hr"] > 0:
        susc_tile = ee_scan.susceptibility_tile(lat, lon, fire_date, peak["est_i15_mm_per_hr"], radius_km)

    return {
        **base, "available": True, "burn_detected": True,
        "source_label": src_label,
        "covariates": cov, "bbox": burn["bbox"], "dnbr_tile_url": burn["dnbr_tile_url"],
        "susceptibility_tile_url": susc_tile,
        "n_steps": len(timeline), "timeline": timeline, "peak": peak,
        "warning": warning, "warning_threshold_i15": threshold,
        "storm_window": [storm_start, storm_end] if storm_start and storm_end else None,
        "forecast_issued": issued, "lead_days": lead_days, "issue_note": issue_note,
        "warning_lead_hours": warn_lead_hours,
        "disaggregation": disagg,
        "disclaimer": (f"EXPERIMENTAL forward-looking outlook from {src_label} FORECAST rainfall "
                       "(model output, not what actually fell). Coarse resolution; not validated "
                       "for real-world use."),
    }
