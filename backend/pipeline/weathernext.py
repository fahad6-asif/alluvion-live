"""
OPTIONAL, EXPERIMENTAL forward-looking rainfall (build brief section 6).

WeatherNext 2 is a named tool but carries three real traps, so it is NOT part of
the validated pipeline and NEVER on the demo critical path:

  1. ACCESS IS GATED. The Earth Engine asset requires a Google data-request form;
     it may be unavailable at build time. The app must not depend on it.

  2. RESOLUTION MISMATCH (the important one). The USGS model needs peak 15-minute
     rainfall INTENSITY (I15). WeatherNext 2's precip band is
     `total_precipitation_6hr` — a 6-HOUR TOTAL at ~28 km. You cannot recover a
     true 15-minute peak from a 6-hour total without a disaggregation ASSUMPTION.
     So any WeatherNext-driven I15 is an ESTIMATE built on an assumption, not a
     measurement. The assumption is made explicit below and labeled in the UI.

  3. TERMS OF USE state the data is "not intended, validated, or approved for real
     world use." Output must never be presented as an operational forecast.

If Earth Engine + WeatherNext access are present, `estimate_i15()` pulls the
6-hour precip for the AOI and converts it via a stated assumption. Otherwise the
endpoint returns `available: false` with this explanation, and the app is fine.
"""

from __future__ import annotations

import os

# --- Disaggregation assumption (MADE EXPLICIT) -----------------------------------
# We assume the 6-hour total falls under a triangular hyetograph whose peak
# 15-minute intensity is PEAK_FACTOR x the mean intensity over the 6 hours.
# This is a coarse, defensible placeholder — NOT a measurement.
PEAK_FACTOR = 6.0
WINDOW_HOURS = 6.0

DISAGGREGATION_NOTE = (
    f"Estimated I15 = (6-hour total / {WINDOW_HOURS} h) x {PEAK_FACTOR} peak factor. "
    "This is an ASSUMPTION-based disaggregation of a 6-hour, ~28 km forecast total "
    "into a peak 15-minute intensity — indicative only, not a measurement."
)


def available() -> bool:
    """True only if Earth Engine is importable AND WeatherNext access is flagged on."""
    if os.environ.get("ENABLE_WEATHERNEXT", "").lower() not in ("1", "true", "yes"):
        return False
    try:
        import ee  # noqa: F401
        return True
    except Exception:
        return False


def status() -> dict:
    if not available():
        return {
            "available": False,
            "reason": (
                "WeatherNext is an optional, experimental forward-looking add-on. It "
                "is disabled here (no Earth Engine auth / access flag). The core app "
                "does not need it."
            ),
            "caveats": [
                "Access is gated behind a Google data-request form.",
                "6-hour, ~28 km total cannot yield a true 15-minute peak intensity.",
                "Terms of use: not validated or approved for real-world use.",
            ],
        }
    return {"available": True, "disaggregation": DISAGGREGATION_NOTE}


def estimate_i15(lat: float, lon: float) -> dict:
    """
    Pull the WeatherNext 6-hour precip total for a point and convert to an
    ESTIMATED I15 via the stated assumption. Returns a clearly-labeled result.
    """
    if not available():
        return {"available": False, **status()}

    import ee

    try:
        ee.Initialize()
    except Exception as e:  # not authenticated
        return {"available": False, "reason": f"Earth Engine not initialized: {e}"}

    col = ee.ImageCollection("projects/gcp-public-data-weathernext/assets/weathernext_2_0_0")
    img = col.sort("system:time_start", False).first()
    pt = ee.Geometry.Point([lon, lat])
    total_6hr_m = (
        img.select("total_precipitation_6hr")
        .reduceRegion(ee.Reducer.mean(), pt, 28000)
        .get("total_precipitation_6hr")
    )
    total_mm = float(ee.Number(total_6hr_m).multiply(1000).getInfo())  # m -> mm
    est_i15 = (total_mm / WINDOW_HOURS) * PEAK_FACTOR
    return {
        "available": True,
        "experimental": True,
        "total_precip_6hr_mm": round(total_mm, 2),
        "estimated_i15_mm_per_hr": round(est_i15, 1),
        "disaggregation": DISAGGREGATION_NOTE,
        "label": "Experimental forecast — estimated intensity, not validated.",
    }
