import React from "react";

// CFSv2 covers 2011+, so historical fires work. WeatherNext is recent-only.
const EXAMPLES = [
  { name: "Thomas Fire → Montecito (2018)", lat: 34.46, lon: -119.63, fire_date: "2017-12-04" },
  { name: "Bobcat Fire → San Gabriels (2021)", lat: 34.24, lon: -117.86, fire_date: "2020-09-06" },
  { name: "Grizzly Creek → Glenwood Cyn (2021)", lat: 39.57, lon: -107.26, fire_date: "2020-08-10" },
  { name: "El Dorado Fire → Oak Glen (2020)", lat: 34.06, lon: -116.94, fire_date: "2020-09-05" },
];

export default function ForecastPanel({ form, setForm, onRun, loading, status, source, setSource }) {
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const src = status?.sources?.[source];
  const enabled = source === "cfsv2" ? true : !!src?.available;

  return (
    <div className="panel scan-panel">
      <h2>🔮 Forecast outlook <span className="exp-tag">EXPERIMENTAL</span></h2>
      <p className="hint" style={{ marginTop: 0 }}>
        Forward-looking: detects the burn scar from satellite, then uses a weather
        <b> FORECAST model's predicted rainfall</b> (not rain that already fell) to
        estimate debris-flow likelihood.
      </p>

      <label className="field"><span>Forecast source</span>
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="cfsv2">NOAA CFSv2 — public, 2011→now (use for 2018/2019)</option>
          <option value="weathernext">Google WeatherNext — recent only, needs access</option>
        </select>
      </label>
      {src?.note && <div className="hint">{src.note}</div>}

      {!enabled && (
        <div className="warn-card"><div className="warn-meta">
          <b>WeatherNext not available.</b> {status?.sources?.weathernext?.note}
        </div></div>
      )}

      <div className="examples">
        <div className="ex-label">Try a fire:</div>
        {EXAMPLES.map((e) => (
          <button key={e.name} className="chip" onClick={() => setForm({ ...form, ...e })}>{e.name}</button>
        ))}
      </div>

      <div className="grid2">
        <label className="field"><span>Latitude</span><input value={form.lat} onChange={set("lat")} /></label>
        <label className="field"><span>Longitude</span><input value={form.lon} onChange={set("lon")} /></label>
      </div>
      <label className="field"><span>Approximate fire date</span>
        <input type="date" value={form.fire_date} onChange={set("fire_date")} /></label>

      <div className="grid2">
        <label className="field"><span>Storm start (optional)</span>
          <input type="date" value={form.storm_start} onChange={set("storm_start")} /></label>
        <label className="field"><span>Storm end (optional)</span>
          <input type="date" value={form.storm_end} onChange={set("storm_end")} /></label>
      </div>
      <div className="hint">Leave storm dates blank to auto-find the strongest forecast storm after the fire.</div>

      <div className="buttons">
        <button className="primary" onClick={onRun} disabled={loading || !enabled}>
          {loading ? "Detecting burn + pulling forecast…" : enabled ? "▶ Run forecast outlook" : "Source not available"}
        </button>
      </div>
    </div>
  );
}
