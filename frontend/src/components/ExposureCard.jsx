import React from "react";

// Occurrence = probability a debris flow happens. Risk = occurrence × worst-threatened
// exposure category. The per-category breakdown lives in the generated AI report.
function fmtPct(p) { return p >= 0.995 ? ">99%" : `${Math.round(p * 100)}%`; }
function tierColor(r) { return r > 0.6 ? "#e31a1c" : r >= 0.3 ? "#ff9900" : r > 0 ? "#2ca25f" : "#5a6b7b"; }

export default function ExposureCard({ occurrence, exposure, loading }) {
  if (loading) return (
    <div className="panel exposure-card"><h2>Occurrence vs. risk</h2>
      <p className="muted">Checking who &amp; what is downstream…</p></div>
  );
  if (occurrence == null || !exposure) return null;

  const risk = occurrence * exposure.exposure_factor;

  return (
    <div className="panel exposure-card">
      <h2>Occurrence vs. risk</h2>
      <div className="ovr">
        <div className="ovr-item">
          <div className="ovr-big">{fmtPct(occurrence)}</div>
          <div className="ovr-label">chance a debris flow <b>occurs</b><br /><span>the hazard (physics)</span></div>
        </div>
        <div className="ovr-x">×&nbsp;exposure</div>
        <div className="ovr-item">
          <div className="ovr-big" style={{ color: tierColor(risk) }}>{fmtPct(risk)}</div>
          <div className="ovr-label">worst-case <b>risk</b> to something<br /><span>occurrence × what's downstream</span></div>
        </div>
      </div>
      <div className="hint">
        The full breakdown — chance of damage to people, property, waterways and farmland,
        each with reasons — is written into the AI advisory below.
      </div>
    </div>
  );
}
