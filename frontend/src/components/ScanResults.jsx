import React from "react";
import { toPST } from "./LiveControls.jsx";

function tierOf(p) { return p > 0.6 ? "High" : p >= 0.3 ? "Moderate" : "Low"; }
// Never show a fake-looking exact 100%; the model saturates at extreme rain.
function fmtPct(p) { return p >= 0.995 ? ">99%" : `${Math.round(p * 100)}%`; }

export default function ScanResults({ scan, showLayer, setShowLayer }) {
  if (!scan) return <div className="panel"><h2>Results</h2><p className="muted">Enter a location and run a scan.</p></div>;

  if (!scan.burn_detected) {
    return (
      <div className="panel">
        <h2>Results</h2>
        <div className="warn-card"><div className="warn-meta">{scan.message}</div></div>
        <div className="hint">Sensor {scan.sensor}
          {scan.n_postfire_scenes != null ? `, ${scan.n_postfire_scenes} post-fire scenes` : ""}.
          {scan.data_available !== false && " The dNBR layer is shown so you can see what the imagery looks like here."}
        </div>
      </div>
    );
  }

  if (scan.storm_found === false) {
    return (
      <div className="panel scan-results">
        <h2>Results</h2>
        <div className="stats">
          <div className="stat"><div className="stat-value">{Math.round(scan.burned_fraction * 100)}%</div>
            <div className="stat-label">Area burned (mod+)</div>
            <div className="stat-sub">dNBR {scan.covariates.dnbr_mean_burned}, {scan.sensor}</div></div>
        </div>
        <div className="warn-card"><div className="warn-meta">{scan.storm_message}</div></div>
        <div className="hint">The burn scar (dNBR) is shown on the map. Set an explicit storm date range to run the rainfall step.</div>
      </div>
    );
  }

  const p = scan.aoi_probability_at_peak;
  const pct = fmtPct(p);
  const cov = scan.covariates;

  return (
    <div className="panel scan-results">
      <h2>Results</h2>
      {scan.warning_msg && <div className="warn-card"><div className="warn-meta">{scan.warning_msg}</div></div>}

      {scan.storm_peak && (
        <div className="storm-banner">
          🌧 <b>Storm identified:</b> {toPST(scan.storm_peak.t)}
          <span className="storm-sub"> — strongest real rain found after the fire ({scan.peak_est_i15_mm_per_hr} mm/hr est. I15)</span>
        </div>
      )}

      <div className="stats">
        <div className="stat"><div className="stat-value">{pct}</div>
          <div className="stat-label">Debris-flow probability</div>
          <div className="stat-sub">at the storm's peak intensity ({tierOf(p)})</div></div>
        <div className="stat"><div className="stat-value">{Math.round(scan.burned_fraction * 100)}%</div>
          <div className="stat-label">Area burned (mod+)</div>
          <div className="stat-sub">dNBR {cov.dnbr_mean_burned}, {scan.sensor}</div></div>
        <div className="stat"><div className="stat-value">{scan.peak_est_i15_mm_per_hr}</div>
          <div className="stat-label">Peak rain (mm/hr)</div>
          <div className="stat-sub">est. I15</div></div>
      </div>

      <div className="verdict">
        Detected a real burn scar (<b>{Math.round(scan.burned_fraction * 100)}%</b> of a
        {" "}{scan.radius_km}-km area) from {scan.sensor}. The strongest storm afterward
        peaked <b>{toPST(scan.storm_peak?.t)}</b> at <b>{scan.peak_est_i15_mm_per_hr} mm/hr</b>.
        {scan.threshold_crossed_at ? (
          <> The model's rainfall threshold ({scan.warning_threshold_i15} mm/hr) was first
          crossed <b>{toPST(scan.threshold_crossed_at)}</b> — a warning would have fired then.</>
        ) : (
          <> The real storm never crossed the model's threshold here.</>
        )}
      </div>

      <div className="layer-toggle">
        <span>Map layer:</span>
        <button className={`chip ${showLayer === "susceptibility" ? "on" : ""}`} onClick={() => setShowLayer("susceptibility")}>Debris-flow susceptibility</button>
        <button className={`chip ${showLayer === "dnbr" ? "on" : ""}`} onClick={() => setShowLayer("dnbr")}>Burn severity (dNBR)</button>
      </div>

    </div>
  );
}
