import React from "react";
import { toPST } from "./LiveControls.jsx";

function fmtPct(p) { return p >= 0.995 ? ">99%" : `${Math.round(p * 100)}%`; }
function tierOf(p) { return p > 0.6 ? "High" : p >= 0.3 ? "Moderate" : "Low"; }

export default function ForecastResults({ fc, showLayer, setShowLayer }) {
  if (!fc) return <div className="panel"><h2>Forecast outlook</h2><p className="muted">Enter a recent fire scar and run.</p></div>;

  if (fc.available === false) {
    return <div className="panel"><h2>Forecast outlook</h2>
      <div className="warn-card"><div className="warn-meta">{fc.reason || "WeatherNext not available."}</div></div></div>;
  }
  if (!fc.burn_detected) {
    return <div className="panel"><h2>Forecast outlook</h2>
      <div className="warn-card"><div className="warn-meta">{fc.message}</div></div></div>;
  }

  const peak = fc.peak;
  const tl = fc.timeline || [];
  const maxI = Math.max(...tl.map((s) => s.est_i15_mm_per_hr), 1);

  return (
    <div className="panel scan-results">
      <h2>Forecast outlook <span className="exp-tag">EXPERIMENTAL</span></h2>

      {peak && (
        <div className="storm-banner">
          🌧 <b>Storm identified:</b> {toPST(peak.t)}
          <span className="storm-sub"> — strongest forecast rain in the window ({peak.est_i15_mm_per_hr} mm/hr est. I15)</span>
        </div>
      )}

      <div className="stats">
        <div className="stat"><div className="stat-value">{peak ? fmtPct(peak.probability) : "—"}</div>
          <div className="stat-label">Peak forecast probability</div>
          <div className="stat-sub">{peak ? `${tierOf(peak.probability)}, ${toPST(peak.t)}` : ""}</div></div>
        <div className="stat"><div className="stat-value">{peak ? peak.est_i15_mm_per_hr : "—"}</div>
          <div className="stat-label">Peak forecast rain</div>
          <div className="stat-sub">mm/hr (est. I15)</div></div>
      </div>

      <div className="issue-card">
        {fc.forecast_issued ? (
          <>📅 <b>Forecast issued {toPST(fc.forecast_issued)}</b>
          {fc.lead_days != null && <> — <b>{fc.lead_days} day{fc.lead_days === 1 ? "" : "s"}</b> before the predicted storm peak</>}.</>
        ) : (
          <>📅 <b>Forecast lead:</b> {fc.issue_note}</>
        )}
        {fc.warning_lead_hours != null && fc.warning_lead_hours > 0 && (
          <div className="issue-sub">
            In this forecast, rain crossed the warning threshold{" "}
            <b>{fc.warning_lead_hours >= 24 ? `${(fc.warning_lead_hours / 24).toFixed(1)} days` : `${fc.warning_lead_hours} h`}</b>{" "}
            before its peak — that lead is derived from the forecast series itself.
          </div>
        )}
        {fc.source === "cfsv2" && (!fc.warning_lead_hours) && (
          <div className="issue-sub">
            This coarse CFSv2 forecast crosses the threshold only at its peak — it doesn't
            resolve a gradual lead-up. For true issued-ahead lead times, use WeatherNext.
          </div>
        )}
      </div>

      {fc.susceptibility_tile_url && (
        <div className="layer-toggle">
          <span>Map layer:</span>
          <button className={`chip ${showLayer === "susceptibility" ? "on" : ""}`} onClick={() => setShowLayer("susceptibility")}>Debris-flow susceptibility</button>
          <button className={`chip ${showLayer === "dnbr" ? "on" : ""}`} onClick={() => setShowLayer("dnbr")}>Burn severity (dNBR)</button>
        </div>
      )}

      {fc.warning ? (
        <div className="warn-card">
          <div className="warn-head"><span className="warn-icon">⚠</span>
            <span className="warn-name">Threshold crossed in forecast</span>
            <span className="warn-prob">{fmtPct(fc.warning.probability)}</span></div>
          <div className="warn-meta">Forecast rain exceeds the model threshold ({fc.warning_threshold_i15} mm/hr) around <b>{toPST(fc.warning.t)}</b>.</div>
        </div>
      ) : (
        <div className="hint">The current WeatherNext forecast never crosses the model's threshold at this site over the forecast horizon.</div>
      )}

      {tl.length > 0 && (
        <>
          <div className="top-title" style={{ marginTop: 14 }}>Forecast rainfall intensity</div>
          <div className="rain-graph">
            {tl.map((s, i) => (
              <div key={i} className="rain-bar" style={{ height: `${Math.max(2, (s.est_i15_mm_per_hr / maxI) * 100)}%`, opacity: 1 }}
                title={`${toPST(s.t)} — ${s.est_i15_mm_per_hr} mm/hr, ${Math.round(s.probability * 100)}%`} />
            ))}
          </div>
          <div className="hint">{tl.length} forecast steps (6-hourly). Hover a bar for time / intensity / probability.</div>
        </>
      )}

      <div className="warn-card" style={{ marginTop: 14 }}>
        <div className="warn-meta">{fc.disclaimer}</div>
      </div>
    </div>
  );
}
