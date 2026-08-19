# Alluvion Live

Post-fire debris-flow hazard & downstream-impact engine, running **live on Google Earth
Engine**. This is the deployment build: it has **no demo/synthetic fallback**. If Earth
Engine isn't authenticated, the app shows a clear "not connected" screen instead of
degrading to fake data.

## What it does (3 tabs)

- **🛰 Live hindcast — Jan 2018 Montecito.** Replays the Thomas Fire debris-flow disaster
  *blind*: detects the burn scar from real Sentinel-2 imagery, watches the real GPM IMERG
  storm, and issues warnings before the event — using only data that existed beforehand.
- **🌎 Scan any US location.** Real burn detection + real storm + the USGS Staley-2017 model
  for any US coordinates and fire date.
- **🔮 Forecast (WeatherNext).** Experimental forward-looking outlook using predicted rainfall.

Each result also computes **downstream exposure** (people, buildings, roads, rivers) and can
generate an **AI advisory**.

## Structure

```
alluvion-live/
  backend/    FastAPI + Earth Engine (deploy on Render)   → holds the secret GEE key
  frontend/   React + Leaflet (deploy on Vercel)          → the public link you share
  DEPLOY.md   step-by-step deployment + Earth Engine auth guide
```

## Deploying

See **[DEPLOY.md](DEPLOY.md)** — a beginner, click-by-click walkthrough. In short:
frontend → Vercel, backend → Render, Earth Engine auth via a service-account key set as the
`EE_SERVICE_ACCOUNT_JSON` environment variable on Render.

## Running locally (optional)

**Backend:**
```bash
cd backend
pip install -r requirements.txt
# authenticate once (either the interactive way for local dev...)
earthengine authenticate
# ...or point at a service-account key file:
#   export EE_SERVICE_ACCOUNT_JSON="$(cat /path/to/key.json)"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
# open http://localhost:5173  (dev proxies /api -> http://localhost:8000)
```

If Earth Engine isn't authenticated, `http://localhost:8000/api/live/status` returns
`{"available": false}` and the frontend shows the "not connected" gate — by design.

## Notes
- US-scoped (soil data is US-only). Warning/targeting tool — **not operationally validated**;
  verify against USGS / NWS.
- Authentication is **server-side only**. No visitor logs in; the public link is read-only.
