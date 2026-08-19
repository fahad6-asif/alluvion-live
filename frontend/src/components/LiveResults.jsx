import React from "react";
import { toPST } from "./LiveControls.jsx";

// The actual debris flows struck ~3:30 AM PST, 9 Jan 2018.
const FLOW_TIME_UTC = "2018-01-09T11:30Z";

function leadHours(warnUtc) {
  const w = new Date(warnUtc).getTime();
  const f = new Date(FLOW_TIME_UTC).getTime();
  return (f - w) / 3600000;
}

export default function LiveResults({ data, frame }) {
  if (!data) return <div className="panel"><h2>Warnings</h2><p className="muted">…</p></div>;
  const curT = data.timeline[frame]?.t;
  const curMs = curT ? new Date(curT).getTime() : 0;

  // warnings that have fired at or before the current timestep
  const fired = data.warnings.filter((w) => new Date(w.t).getTime() <= curMs);
  const pending = data.warnings.filter((w) => new Date(w.t).getTime() > curMs);

  return (
    <div className="panel live-results">
      <h2>⚠ Warnings issued (blind)</h2>

      {fired.length === 0 ? (
        <p className="muted">No warnings yet. Press play — watch the burned basins trip as the real storm intensifies.</p>
      ) : (
        fired.map((w) => {
          const lead = leadHours(w.t);
          return (
            <div key={w.name} className="warn-card">
              <div className="warn-head">
                <span className="warn-icon">⚠</span>
                <span className="warn-name">{w.name}</span>
                <span className="warn-prob">{Math.round(w.probability * 100)}%</span>
              </div>
              <div className="warn-meta">
                Issued <b>{toPST(w.t)}</b> · <b>{lead.toFixed(1)} h</b> before the flows
              </div>
            </div>
          );
        })
      )}

      {pending.length > 0 && (
        <div className="pending muted">
          {pending.length} basin{pending.length > 1 ? "s" : ""} not yet warned at this timestep.
        </div>
      )}

      {frame >= data.timeline.length - 1 && (
        <div className="verdict">
          By storm's end the system flagged <b>{data.warnings.length}</b> basins — the
          creeks that produced the deadly 9 Jan 2018 flows — with up to{" "}
          <b>{Math.max(...data.warnings.map((w) => leadHours(w.t))).toFixed(0)} hours</b>{" "}
          of lead time, using only pre-event data.
        </div>
      )}

      <div className="live-notes">
        <div className="ln-title">How this is grounded (and its limits)</div>
        <ul>
          <li><b>Real:</b> burn scar from Sentinel-2 (cutoff {data.blind_cutoff}), SRTM slope, GPM IMERG storm, USGS Staley-2017 equation.</li>
          <li><b>Estimated:</b> I15 = IMERG areal-max × {data.imerg_to_i15_factor} (labeled estimate, not a gauge reading).</li>
          <li><b>Simplified:</b> basins are drainage bands; soil is an OpenLandMap KF proxy. Not operationally validated.</li>
        </ul>
      </div>
    </div>
  );
}
