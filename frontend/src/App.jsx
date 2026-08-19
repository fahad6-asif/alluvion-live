import React, { useEffect, useState, useCallback } from "react";
import { api } from "./api.js";
import MapView from "./components/MapView.jsx";
import LiveControls from "./components/LiveControls.jsx";
import LiveResults from "./components/LiveResults.jsx";
import ScanPanel from "./components/ScanPanel.jsx";
import ScanResults from "./components/ScanResults.jsx";
import ForecastPanel from "./components/ForecastPanel.jsx";
import ForecastResults from "./components/ForecastResults.jsx";
import ExposureCard from "./components/ExposureCard.jsx";
import AdvisoryReport from "./components/AdvisoryReport.jsx";
import { toPST } from "./components/LiveControls.jsx";

// Validate a location form before hitting the (slow) EE endpoints.
function badInput(f) {
  const la = parseFloat(f.lat), lo = parseFloat(f.lon);
  if (!Number.isFinite(la) || !Number.isFinite(lo))
    return "Enter numeric latitude and longitude (e.g. 34.46 and -119.63) — no letters, symbols, or spaces.";
  if (la < -90 || la > 90) return "Latitude must be between -90 and 90.";
  if (lo < -180 || lo > 180) return "Longitude must be between -180 and 180.";
  if (!f.fire_date) return "Pick an approximate fire date.";
  return null;
}

function ringToBounds(ring) {
  if (!ring) return null;
  const xs = ring.map((c) => c[0]), ys = ring.map((c) => c[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

// ---- Full-screen gate shown when Earth Engine is not connected ----
// This build has NO demo/synthetic fallback: without Earth Engine there is
// nothing to show, so we say so plainly instead of degrading silently.
function NotConnected({ note, checking }) {
  return (
    <div className="gate">
      <div className="gate-card">
        <div className="gate-mark">🛰</div>
        <h1><span className="brand">Alluvion</span> <span className="brand-sub">Live</span></h1>
        {checking ? (
          <>
            <p className="gate-status">Connecting to Google Earth Engine…</p>
            <div className="gate-spinner" />
          </>
        ) : (
          <>
            <p className="gate-status gate-error">Live satellite mode is not connected.</p>
            <p className="gate-note">
              {note || "This deployment requires Google Earth Engine authentication on the backend."}
            </p>
            <p className="gate-hint">
              If you are the operator: check that the backend is running and that a valid
              Earth Engine service-account key is configured. See <code>DEPLOY.md</code>.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default function App() {
  // earth engine gate
  const [liveStatus, setLiveStatus] = useState(null);   // null = still checking
  const eeAvailable = liveStatus?.available;

  const [perimeter, setPerimeter] = useState(null);
  const [error, setError] = useState(null);

  // live hindcast
  const [liveData, setLiveData] = useState(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [phase, setPhase] = useState("detect");
  const [detectStep, setDetectStep] = useState(0);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  // scan-any-location
  const [scanForm, setScanForm] = useState({ lat: "34.46", lon: "-119.63", fire_date: "2017-12-04", storm_start: "", storm_end: "" });
  const [scanData, setScanData] = useState(null);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanLayer, setScanLayer] = useState("susceptibility");

  // forecast (CFSv2 / WeatherNext)
  const [fcStatus, setFcStatus] = useState(null);
  const [fcSource, setFcSource] = useState("cfsv2");
  const [fcForm, setFcForm] = useState({ lat: "34.46", lon: "-119.63", fire_date: "2017-12-04", storm_start: "", storm_end: "" });
  const [fcData, setFcData] = useState(null);
  const [fcLoading, setFcLoading] = useState(false);
  const [fcLayer, setFcLayer] = useState("susceptibility");

  // downstream exposure / risk
  const [exposure, setExposure] = useState(null);
  const [exposureLoading, setExposureLoading] = useState(false);

  // AI advisory workflow
  const [reportStatus, setReportStatus] = useState(null);
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [recipient, setRecipient] = useState("");
  const [sending, setSending] = useState(false);
  const [emailResult, setEmailResult] = useState(null);

  const [mode, setMode] = useState("live");

  // bootstrap — the gate hinges entirely on /api/live/status
  useEffect(() => {
    (async () => {
      try {
        const s = await api.liveStatus();
        setLiveStatus(s);
      } catch (e) {
        // Backend unreachable is, for this build, the same as "not connected".
        setLiveStatus({ available: false, note: `Cannot reach the backend API (${e.message}).` });
      }
      try { setFcStatus(await api.forecastStatus()); } catch { setFcStatus(null); }
      try { setReportStatus(await api.reportStatus()); } catch { setReportStatus(null); }
    })();
  }, []);

  // Thomas Fire perimeter outline (static real geography, bundled with the app).
  useEffect(() => {
    if (!eeAvailable) return;
    fetch(`${import.meta.env.BASE_URL}thomas_perimeter.geojson`)
      .then((r) => (r.ok ? r.json() : null)).then(setPerimeter).catch(() => setPerimeter(null));
  }, [eeAvailable]);

  // load live hindcast
  useEffect(() => {
    if (!eeAvailable || mode !== "live" || liveData || liveLoading) return;
    setLiveLoading(true); setError(null);
    api.liveReplay().then((d) => { setLiveData(d); setFrame(0); })
      .catch((e) => setError(`Live hindcast failed: ${e.message}`))
      .finally(() => setLiveLoading(false));
  }, [mode, eeAvailable, liveData, liveLoading]);

  // playback loop
  useEffect(() => {
    if (!playing || mode !== "live" || phase !== "storm" || !liveData) return;
    const n = liveData.timeline.length;
    const id = setInterval(() => setFrame((f) => (f >= n - 1 ? (setPlaying(false), f) : f + 1)), Math.round(180 / speed));
    return () => clearInterval(id);
  }, [playing, mode, phase, liveData, speed]);

  // fetch downstream exposure for whichever tab has a result (keyed on AOI center)
  useEffect(() => {
    if (!eeAvailable) return;
    let center = null;
    if (mode === "live" && liveData?.bbox)
      center = [(liveData.bbox[1] + liveData.bbox[3]) / 2, (liveData.bbox[0] + liveData.bbox[2]) / 2];
    else if (mode === "scan" && scanData?.burn_detected) center = [scanData.lat, scanData.lon];
    else if (mode === "forecast" && fcData?.burn_detected) center = [fcData.lat, fcData.lon];
    setReport(null); setEmailResult(null);   // a new AOI invalidates the old advisory
    if (!center) { setExposure(null); return; }
    setExposureLoading(true);
    api.exposure({ lat: center[0], lon: center[1] })
      .then(setExposure).catch(() => setExposure(null))
      .finally(() => setExposureLoading(false));
  }, [mode, eeAvailable, liveData, scanData, fcData]);

  const runScan = useCallback(async () => {
    const bad = badInput(scanForm);
    if (bad) { setError(bad); return; }
    setScanLoading(true); setError(null); setScanData(null);
    try {
      const d = await api.scan({
        lat: parseFloat(scanForm.lat), lon: parseFloat(scanForm.lon), fire_date: scanForm.fire_date,
        storm_start: scanForm.storm_start || undefined, storm_end: scanForm.storm_end || undefined,
      });
      setScanData(d);
      setScanLayer("susceptibility");
    } catch (e) { setError(`Scan failed: ${e.message}`); }
    finally { setScanLoading(false); }
  }, [scanForm]);

  const runForecast = useCallback(async () => {
    const bad = badInput(fcForm);
    if (bad) { setError(bad); return; }
    setFcLoading(true); setError(null); setFcData(null);
    try { setFcData(await api.forecast({ lat: parseFloat(fcForm.lat), lon: parseFloat(fcForm.lon), fire_date: fcForm.fire_date, source: fcSource, storm_start: fcForm.storm_start || undefined, storm_end: fcForm.storm_end || undefined })); }
    catch (e) { setError(`Forecast failed: ${e.message}`); }
    finally { setFcLoading(false); }
  }, [fcForm, fcSource]);

  // ---- render the gate until Earth Engine is confirmed available ----
  if (liveStatus === null) return <NotConnected checking />;
  if (!eeAvailable) return <NotConnected note={liveStatus?.note} />;

  // ---------- derive map inputs ----------
  const live = mode === "live", scan = mode === "scan", forecast = mode === "forecast";
  const liveBounds = liveData?.bbox ? [...liveData.bbox] : null;

  let rasterTileUrl = null, rasterLabel = null, showBasins = false, basinProbs = null,
      highlightBasins = false, bounds = null;

  if (live) {
    if (phase === "detect") {
      rasterTileUrl = [liveData?.prefire_rgb_tile_url, liveData?.postfire_rgb_tile_url, liveData?.dnbr_tile_url][detectStep];
      rasterLabel = detectStep === 2 ? "Burn severity (dNBR), live Sentinel-2" : null;
      showBasins = detectStep === 2; highlightBasins = detectStep === 2;
    } else {
      rasterTileUrl = liveData?.dnbr_tile_url; rasterLabel = "Burn severity (dNBR), live Sentinel-2";
      showBasins = true; basinProbs = liveData?.timeline[frame]?.prob;
    }
    bounds = liveBounds;
  } else if (scan) {
    const hasSusc = scanData?.susceptibility_tile_url;
    const useSusc = scanLayer === "susceptibility" && hasSusc;
    rasterTileUrl = scanData ? (useSusc ? scanData.susceptibility_tile_url : scanData.dnbr_tile_url) : null;
    rasterLabel = scanData ? (useSusc ? "Debris-flow susceptibility (gridded)" : "Burn severity (dNBR)") : null;
    bounds = scanData?.bbox ? ringToBounds(scanData.bbox) : null;
  } else if (forecast) {
    const hasSusc = fcData?.susceptibility_tile_url;
    const useSusc = fcLayer === "susceptibility" && hasSusc;
    rasterTileUrl = fcData ? (useSusc ? fcData.susceptibility_tile_url : fcData.dnbr_tile_url) : null;
    rasterLabel = fcData ? (useSusc ? "Debris-flow susceptibility (gridded)" : "Burn severity (dNBR)") : null;
    bounds = fcData?.bbox ? ringToBounds(fcData.bbox) : null;
  }

  // occurrence probability feeding the risk calc (per active tab)
  let occurrence = null;
  if (live && liveData) {
    let mx = 0;
    liveData.timeline.forEach((s) => Object.values(s.prob || {}).forEach((p) => { if (p > mx) mx = p; }));
    occurrence = mx;
  } else if (scan && scanData?.burn_detected) {
    occurrence = scanData.aoi_probability_at_peak;
  } else if (forecast && fcData?.burn_detected) {
    occurrence = fcData.peak?.probability ?? null;
  }
  const showExposure = live || scan || forecast;

  // assemble the structured context the AI advisory workflow reasons over
  const buildContext = () => {
    const overall_risk = exposure ? occurrence * exposure.exposure_factor : occurrence;
    let fire_name = "burned area", location = "", storm = {};
    if (live) { fire_name = liveData?.name || "Thomas Fire (2018 Montecito)"; location = "Montecito, CA";
      storm = { peak_i15: liveData?.peak?.est_i15_mm_per_hr, peak_time: liveData?.peak?.t, peak_time_label: toPST(liveData?.peak?.t), source: "observed satellite rainfall (IMERG)" }; }
    else if (scan) { fire_name = "Scanned burn scar"; location = `${scanData?.lat}, ${scanData?.lon}`;
      storm = { peak_i15: scanData?.peak_est_i15_mm_per_hr, peak_time: scanData?.storm_peak?.t, peak_time_label: toPST(scanData?.storm_peak?.t), source: "observed satellite rainfall (IMERG)" }; }
    else if (forecast) { fire_name = "Forecast site"; location = `${fcData?.lat}, ${fcData?.lon}`;
      storm = { peak_i15: fcData?.peak?.est_i15_mm_per_hr, peak_time: fcData?.peak?.t, peak_time_label: toPST(fcData?.peak?.t), source: fcData?.source_label || "forecast" }; }
    return { fire_name, location, mode, occurrence, overall_risk,
             risk_categories: exposure?.risk_categories || {}, exposure_metrics: exposure?.metrics || {},
             storm, satellite_thumb_url: exposure?.satellite_thumb_url, aoi_bbox: exposure?.aoi_bbox };
  };

  const generateReport = async () => {
    setReportLoading(true); setEmailResult(null); setError(null);
    try { const r = await api.report({ context: buildContext(), send: false }); setReport(r.report); }
    catch (e) { setError(`Advisory failed: ${e.message}`); }
    finally { setReportLoading(false); }
  };
  const sendReport = async () => {
    setSending(true); setError(null);
    try { const r = await api.report({ context: buildContext(), send: true, recipient }); setReport(r.report); setEmailResult(r.email); }
    catch (e) { setError(`Send failed: ${e.message}`); }
    finally { setSending(false); }
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="title-block">
          <h1><span className="brand">Alluvion</span> <span className="brand-sub">Post-Fire Hazard &amp; Downstream Impact Engine</span></h1>
          <p className="subtitle">
            Alluvion translates post-fire debris-flow science into targeted downstream
            emergency action <i>before the storm hits</i>.
          </p>
        </div>
        <div className="badges">
          {forecast && <span className="badge badge-exp" title="Experimental forecast, not validated">⚗ EXPERIMENTAL</span>}
          <span className="badge badge-live">🛰 LIVE — Earth Engine</span>
        </div>
      </header>

      <div className="mode-switch">
        <button className={live ? "active" : ""} onClick={() => setMode("live")}>🛰 Live hindcast — Jan 2018 Montecito</button>
        <button className={scan ? "active" : ""} onClick={() => { setMode("scan"); setPlaying(false); }}>🌎 Scan any US location</button>
        <button className={forecast ? "active" : ""} onClick={() => { setMode("forecast"); setPlaying(false); }}>🔮 Forecast (WeatherNext)</button>
      </div>

      {error && <div className="error-bar">{error}</div>}

      <div className="layout">
        <div className="left-col">
          {live && (
            <LiveControls data={liveData} phase={phase} setPhase={setPhase}
              detectStep={detectStep} setDetectStep={setDetectStep}
              frame={frame} setFrame={setFrame} playing={playing} setPlaying={setPlaying}
              speed={speed} setSpeed={setSpeed} />
          )}
          {scan && <ScanPanel form={scanForm} setForm={setScanForm} onRun={runScan} loading={scanLoading} />}
          {forecast && <ForecastPanel form={fcForm} setForm={setFcForm} onRun={runForecast} loading={fcLoading} status={fcStatus} source={fcSource} setSource={setFcSource} />}
        </div>

        <MapView
          live={live || scan}
          rasterTileUrl={rasterTileUrl} rasterLabel={rasterLabel}
          showBasins={showBasins} basins={liveData?.basins} basinProbs={basinProbs} highlightBasins={highlightBasins}
          perimeter={perimeter} bounds={bounds} exposure={showExposure ? exposure : null} />

        <div className="right-col">
          {live && <LiveResults data={liveData} frame={frame} />}
          {scan && <ScanResults scan={scanData} showLayer={scanLayer} setShowLayer={setScanLayer} />}
          {forecast && <ForecastResults fc={fcData} showLayer={fcLayer} setShowLayer={setFcLayer} />}
          {showExposure && occurrence != null && (
            <ExposureCard occurrence={occurrence} exposure={exposure} loading={exposureLoading} />
          )}
          {showExposure && occurrence != null && (
            <AdvisoryReport
              occurrence={occurrence} status={reportStatus} report={report} loading={reportLoading}
              onGenerate={generateReport} recipient={recipient} setRecipient={setRecipient}
              onSend={sendReport} sending={sending} emailResult={emailResult} />
          )}
        </div>
      </div>

      <footer className="app-footer">
        <div className="credits">
          <div className="credit-col">
            <b>Hazard model</b>
            <span>USGS Staley et al. (2017) M1</span>
            <span>Gartner (2014) volume · Cannon (2010) class</span>
          </div>
          <div className="credit-col">
            <b>Earth observation</b>
            <span>Sentinel-2 · Landsat 8 (burn scar)</span>
            <span>SRTM (terrain) · GPM IMERG (rain)</span>
            <span>NOAA CFSv2 · WeatherNext (forecast)</span>
          </div>
          <div className="credit-col">
            <b>Exposure &amp; impact</b>
            <span>WorldPop · GHSL (people/built)</span>
            <span>TIGER roads · HydroSHEDS rivers</span>
            <span>USDA CDL farmland · Google Places</span>
          </div>
          <div className="credit-col">
            <b>Platform &amp; AI</b>
            <span>Google Earth Engine</span>
            <span>Gemini (advisory) · OpenLandMap soil</span>
          </div>
        </div>
        <div className="credit-note">US-scoped (soil data). Warning/targeting tool — not operationally validated; verify against USGS / NWS.</div>
      </footer>
    </div>
  );
}
