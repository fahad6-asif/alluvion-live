import React from "react";

// UTC "YYYY-MM-DDTHH:mmZ" -> Montecito local (PST, UTC-8) label.
export function toPST(utc, opts = {}) {
  if (!utc) return "—";
  const d = new Date(utc);
  const p = new Date(d.getTime() - 8 * 3600 * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  const mon = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][p.getUTCMonth()];
  let h = p.getUTCHours();
  const ap = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  const time = `${pad(h)}:${pad(p.getUTCMinutes())} ${ap}`;
  return opts.timeOnly ? `${time} PST` : `${mon} ${p.getUTCDate()}, ${time} PST`;
}

const SPEEDS = [0.5, 1, 2, 4];

const DETECT_STEPS = [
  { title: "1 · Before the fire", cap: "October 2017 — healthy chaparral on the Santa Ynez front, directly above Montecito. True-color Sentinel-2." },
  { title: "2 · After the fire", cap: "Late December 2017 — the Thomas Fire has stripped the slopes. The dark burn scar is visible from space, weeks before any rain." },
  { title: "3 · Burn severity (dNBR)", cap: "Differencing before vs. after gives dNBR (red = severe burn). Five steep, severely-burned creeks are now primed — the model flags them before a single drop falls." },
];

function frameNearest(timeline, utc) {
  if (!utc) return -1;
  const target = new Date(utc).getTime();
  let best = 0, bestd = Infinity;
  timeline.forEach((s, i) => { const d = Math.abs(new Date(s.t).getTime() - target); if (d < bestd) { bestd = d; best = i; } });
  return best;
}

export default function LiveControls({ data, phase, setPhase, detectStep, setDetectStep, frame, setFrame, playing, setPlaying, speed, setSpeed }) {
  if (!data) return <div className="panel"><h2>Live hindcast</h2><p className="muted">Loading real Earth Engine data… (first run pulls live satellite imagery, ~10 s)</p></div>;

  // ---------- Detection walkthrough phase ----------
  if (phase === "detect") {
    const step = DETECT_STEPS[detectStep];
    return (
      <div className="panel live-controls">
        <h2>🛰 Step 1 — detect the burn scar</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          Using only imagery from <b>before</b> the storm (cutoff {data.blind_cutoff}),
          the system sees the fire from space. Step through the detection:
        </p>
        <div className="detect-card">
          <div className="detect-title">{step.title}</div>
          <div className="detect-cap">{step.cap}</div>
        </div>
        <div className="buttons" style={{ flexDirection: "row" }}>
          <button className="chip" disabled={detectStep === 0} onClick={() => setDetectStep(detectStep - 1)}>◀ Back</button>
          {detectStep < DETECT_STEPS.length - 1 ? (
            <button className="primary" onClick={() => setDetectStep(detectStep + 1)}>Next ▶</button>
          ) : (
            <button className="primary" onClick={() => { setPhase("storm"); setFrame(0); }}>▶ Now watch the storm</button>
          )}
        </div>
        <div className="dots">
          {DETECT_STEPS.map((_, i) => <span key={i} className={`dot2 ${i === detectStep ? "on" : ""}`} />)}
        </div>
      </div>
    );
  }

  // ---------- Storm replay phase ----------
  const tl = data.timeline;
  const cur = tl[frame] || tl[0];
  const maxRain = Math.max(...tl.map((s) => s.est_i15_mm_per_hr), 1);
  const flowIdx = frameNearest(tl, data.flow_onset_utc);
  const peakIdx = frameNearest(tl, data.peak?.t);

  return (
    <div className="panel live-controls">
      <h2>🛰 Step 2 — watch the storm, blind</h2>
      <p className="hint" style={{ marginTop: 0 }}>
        Real GPM IMERG rainfall, replayed at true times. The model never sees the outcome.
      </p>

      <div className="clock">
        <div className="clock-time">{toPST(cur.t)}</div>
        <div className="clock-sub">Rain intensity now: <b>{cur.est_i15_mm_per_hr} mm/hr</b> (est. I15)</div>
      </div>

      <div className="rain-graph">
        {tl.map((s, i) => {
          const h = Math.max(2, (s.est_i15_mm_per_hr / maxRain) * 100);
          let cls = "rain-bar";
          if (i === frame) cls += " cur";
          if (i === flowIdx) cls += " flow";
          if (i === peakIdx) cls += " peak";
          return <div key={i} className={cls} style={{ height: `${h}%`, opacity: i <= frame ? 1 : 0.28 }} title={`${toPST(s.t)} — ${s.est_i15_mm_per_hr} mm/hr`} />;
        })}
      </div>
      <div className="graph-legend">
        <span><span className="tick flow" /> flows struck ~3:30 AM</span>
        <span><span className="tick peak" /> rainfall peak</span>
      </div>

      <input type="range" min="0" max={tl.length - 1} value={frame}
        onChange={(e) => { setPlaying(false); setFrame(Number(e.target.value)); }} className="timeline" />

      <div className="buttons" style={{ flexDirection: "row", flexWrap: "wrap" }}>
        <button className="primary" onClick={() => setPlaying(!playing)}>{playing ? "⏸ Pause" : "▶ Play the storm"}</button>
        <button className="chip" onClick={() => { setPlaying(false); setFrame(0); }}>⏮ Reset</button>
      </div>

      <div className="speed-row">
        <span>Speed:</span>
        {SPEEDS.map((s) => (
          <button key={s} className={`chip ${speed === s ? "on" : ""}`} onClick={() => setSpeed(s)}>{s}×</button>
        ))}
      </div>

      <button className="linkbtn" onClick={() => { setPlaying(false); setPhase("detect"); }}>◀ Back to burn-scar detection</button>

      <div className="hint" style={{ marginTop: 10 }}>
        <b>Peak</b> ({toPST(data.peak?.t)}, {data.peak?.est_i15_mm_per_hr} mm/hr) lands
        <b> during</b> the flows — that's the trigger. The <b>warnings</b> (right) fire
        hours earlier, when the burned basins first cross their rainfall threshold.
      </div>
    </div>
  );
}
