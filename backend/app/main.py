"""
FastAPI backend for Alluvion Live — the GEE-ONLY deployment.

Every feature here runs on REAL Google Earth Engine data. There is NO synthetic
fallback: if Earth Engine is not authenticated, the live endpoints return 503 and
the frontend shows a "not connected" gate instead of degrading to demo data.

Endpoints:
  GET  /api/health           -> service + Earth Engine status
  GET  /api/live/status      -> is the live hindcast available?
  GET  /api/live/replay      -> full blind Thomas Fire / Montecito hindcast
  POST /api/scan             -> live burn+storm scan for any US location
  GET  /api/forecast/status  -> forward-looking forecast availability
  POST /api/forecast         -> experimental forecast (CFSv2 / WeatherNext)
  POST /api/exposure         -> downstream people/buildings/roads exposure
  GET  /api/report/status    -> AI advisory + email wiring
  POST /api/report           -> generate (and optionally email) an AI advisory

Authentication to Earth Engine is server-side only (a service-account key held in
an env var); no visitor ever logs in. See DEPLOY.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# make `pipeline` importable when run as `uvicorn app.main:app`
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

app = FastAPI(
    title="Alluvion Live — Post-Fire Debris-Flow API (Earth Engine)",
    version="1.0.0",
    description=(
        "Live Google Earth Engine post-fire debris-flow workflow. "
        "US-scoped, not operationally validated. Requires Earth Engine auth."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # public read-only demo; no auth, no user data
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    """Service + Earth Engine status (no synthetic engine in this build)."""
    from pipeline import ee_engine
    return {
        "status": "ok",
        "earth_engine_available": ee_engine.available(),
        "engine": "live-earthengine",
    }


@app.get("/api/live/status")
def live_status() -> dict:
    """Is the live Earth Engine hindcast available (authenticated + reachable)?"""
    from pipeline import ee_engine
    ok = ee_engine.available()
    return {
        "available": ok,
        "engine": "live-earthengine" if ok else "unavailable",
        "note": (
            "Runs the pipeline BLIND on real archived satellite + precipitation data "
            "(temporal holdout). Detects the burn scar from Sentinel-2, watches the "
            "real storm in GPM IMERG, and warns before the event."
        ) if ok else (
            "Live satellite mode is not connected: the backend could not authenticate "
            "to Google Earth Engine. This deployment requires a valid Earth Engine "
            "service-account key (see DEPLOY.md)."
        ),
    }


@app.get("/api/live/replay")
def live_replay(force: bool = False) -> dict:
    """
    Full blind hindcast for the Thomas Fire: real per-basin burn/terrain/soil
    covariates, the real storm time-series, per-timestep probabilities, and the
    warnings the system would have issued — with lead time before the 9 Jan 2018
    Montecito debris flows. Cached (the EE calls are the slow part).
    """
    from pipeline import ee_engine
    if not ee_engine.available():
        raise HTTPException(status_code=503, detail="Earth Engine not available on the backend.")
    return ee_engine.run_replay(force=force)


@app.post("/api/scan")
def scan(req: dict) -> dict:
    """
    General live scan: real burn detection + real storm + model, for ANY US
    coordinates + approximate fire date. Body: {lat, lon, fire_date,
    storm_start?, storm_end?, radius_km?}.
    """
    from pipeline import ee_engine, ee_scan
    if not ee_engine.available():
        raise HTTPException(status_code=503, detail="Earth Engine not available on the backend.")
    try:
        lat = float(req["lat"]); lon = float(req["lon"]); fire_date = str(req["fire_date"])
    except Exception:
        raise HTTPException(status_code=422, detail="Require numeric lat, lon and fire_date=YYYY-MM-DD.")
    try:
        return ee_scan.scan(
            lat, lon, fire_date,
            storm_start=req.get("storm_start"), storm_end=req.get("storm_end"),
            radius_km=float(req.get("radius_km", 6.0)),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")


@app.get("/api/forecast/status")
def forecast_status() -> dict:
    """Is the WeatherNext forward-looking forecast accessible from this account?"""
    from pipeline import ee_forecast
    return ee_forecast.status()


@app.post("/api/forecast")
def forecast(req: dict) -> dict:
    """
    EXPERIMENTAL forward-looking outlook: real burn scar + WeatherNext PREDICTED
    rainfall -> debris-flow likelihood. Body: {lat, lon, fire_date, radius_km?}.
    """
    from pipeline import ee_engine, ee_forecast
    if not ee_engine.available():
        raise HTTPException(status_code=503, detail="Earth Engine not available on the backend.")
    try:
        lat = float(req["lat"]); lon = float(req["lon"]); fire_date = str(req["fire_date"])
    except Exception:
        raise HTTPException(status_code=422, detail="Require numeric lat, lon and fire_date=YYYY-MM-DD.")
    try:
        return ee_forecast.forecast(
            lat, lon, fire_date,
            source=req.get("source", "cfsv2"),
            radius_km=float(req.get("radius_km", 6.0)),
            storm_start=req.get("storm_start"), storm_end=req.get("storm_end"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecast failed: {e}")


@app.post("/api/exposure")
def exposure(req: dict) -> dict:
    """
    Downstream exposure/impact for an AOI center: people, buildings, roads, rivers,
    critical facilities in the debris-flow runout zone + an exposure factor.
    Body: {lat, lon, radius_km?}. Occurrence x exposure_factor = risk.
    """
    from pipeline import ee_engine, ee_exposure
    if not ee_engine.available():
        raise HTTPException(status_code=503, detail="Earth Engine not available on the backend.")
    try:
        lat = float(req["lat"]); lon = float(req["lon"])
    except Exception:
        raise HTTPException(status_code=422, detail="Require numeric lat and lon.")
    try:
        return ee_exposure.exposure(lat, lon, radius_km=float(req.get("radius_km", 6.0)))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Exposure failed: {e}")


@app.get("/api/report/status")
def report_status() -> dict:
    """What's wired for the AI advisory workflow: Gemini + email."""
    from pipeline import report, mailer
    return {
        "gemini_available": report.gemini_available(),
        "occurrence_threshold": report.OCCURRENCE_REPORT_THRESHOLD,
        "email": mailer.status(),
    }


@app.post("/api/report")
def make_report(req: dict) -> dict:
    """
    Agentic advisory workflow: given an assessment context, generate an AI report
    (only if occurrence >= threshold) and OPTIONALLY email it. The email step only
    runs when `send` is true, a recipient is given, and the user's own mail creds are
    configured — nothing is sent autonomously.
    Body: {context: {...}, send?: bool, recipient?: str}
    """
    from pipeline import report, mailer
    context = req.get("context") or {}
    result = report.generate(context)

    email_result = None
    if req.get("send") and result.get("above_threshold") and result.get("text"):
        subject = (f"[{result['severity']}] Debris-flow advisory — "
                   f"{context.get('fire_name', 'burned area')}")
        email_result = mailer.send(req.get("recipient", ""), subject, result["text"])

    return {"report": result, "email": email_result}


@app.get("/")
def root() -> dict:
    return {"service": "alluvion-live", "docs": "/docs", "health": "/api/health"}
