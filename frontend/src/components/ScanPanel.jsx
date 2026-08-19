import React from "react";

// Real, verified US post-fire debris-flow settings — one click loads coords+date
// so you can immediately "capture" a real event (each pulls its own live data).
const EXAMPLES = [
  { name: "Thomas Fire → Montecito (2018)", lat: 34.46, lon: -119.63, fire_date: "2017-12-04" },
  { name: "Bobcat Fire → San Gabriels (2021)", lat: 34.24, lon: -117.86, fire_date: "2020-09-06" },
  { name: "Grizzly Creek → Glenwood Cyn (2021)", lat: 39.57, lon: -107.26, fire_date: "2020-08-10" },
  { name: "El Dorado Fire → Oak Glen (2020)", lat: 34.06, lon: -116.94, fire_date: "2020-09-05" },
];

export default function ScanPanel({ form, setForm, onRun, loading }) {
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="panel scan-panel">
      <h2>🌎 Scan any US location</h2>
      <p className="hint" style={{ marginTop: 0 }}>
        Enter coordinates and an approximate fire date. It pulls the <b>real</b>
        satellite imagery and the <b>real</b> rainfall for that place/time, detects
        the burn scar, and runs the model — capturing the event if one happened.
      </p>

      <div className="examples">
        <div className="ex-label">Try a real event:</div>
        {EXAMPLES.map((e) => (
          <button key={e.name} className="chip" onClick={() => setForm({ ...form, ...e })}>{e.name}</button>
        ))}
      </div>

      <div className="grid2">
        <label className="field"><span>Latitude</span>
          <input value={form.lat} onChange={set("lat")} placeholder="34.46" /></label>
        <label className="field"><span>Longitude</span>
          <input value={form.lon} onChange={set("lon")} placeholder="-119.63" /></label>
      </div>
      <label className="field"><span>Approximate fire date</span>
        <input type="date" value={form.fire_date} onChange={set("fire_date")} /></label>

      <div className="grid2">
        <label className="field"><span>Storm start (optional)</span>
          <input type="date" value={form.storm_start} onChange={set("storm_start")} /></label>
        <label className="field"><span>Storm end (optional)</span>
          <input type="date" value={form.storm_end} onChange={set("storm_end")} /></label>
      </div>
      <div className="hint">Leave storm dates blank to auto-find the most intense rain in the ~8 months after the fire.</div>

      <div className="buttons">
        <button className="primary" onClick={onRun} disabled={loading}>
          {loading ? "Pulling live satellite + rainfall… (~30 s)" : "▶ Run live scan"}
        </button>
      </div>
    </div>
  );
}
