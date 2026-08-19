import React, { useEffect, useRef } from "react";
import L from "leaflet";

// Tier colors — MUST match backend pipeline/model.py (build brief section 5.5).
const TIER = { Low: "#2ca25f", Moderate: "#ff9900", High: "#e31a1c" };

const BASEMAP_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const BASEMAP_ATTR = "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics";

function segmentStyle(feature) {
  const p = feature.properties || {};
  return { color: p.color || TIER[p.tier] || "#888", weight: p.is_main_creek ? 6 : 4, opacity: 0.95, lineCap: "round" };
}
const inundationStyle = { color: "#000", weight: 2, dashArray: "6 5", fill: true, fillColor: "#000", fillOpacity: 0.08 };
const perimeterStyle = { color: "#ffcc00", weight: 2, dashArray: "4 4", fill: true, fillColor: "#ffcc00", fillOpacity: 0.06 };

function basinFill(prob, highlight) {
  const c = prob == null ? "#3b82f6" : prob > 0.6 ? TIER.High : prob >= 0.3 ? TIER.Moderate : TIER.Low;
  return { color: highlight ? "#fff" : "#111", weight: highlight ? 2.5 : 1, fillColor: c, fillOpacity: prob == null ? 0.15 : 0.6 };
}

function segPopup(p) {
  const pct = p.probability != null ? `${Math.round(p.probability * 100)}%` : "—";
  return `<strong>${p.name || p.seg_id || "Segment"}</strong><br/>Probability: <b>${pct}</b> (${p.tier || "—"})<br/><small>at I15 = ${p.i15_mm_per_hr ?? "?"} mm/hr</small>`;
}
function basinPopup(p) {
  const pct = p.prob != null ? `${Math.round(p.prob * 100)}%` : "—";
  return `<strong>${p.name}</strong><br/>Probability: <b>${pct}</b><br/><small>dNBR=${p.dnbr} · T=${p.T} · KF=${p.S}</small><br/><small>warns at est. I15 ≥ ${p.threshold} mm/hr</small>`;
}

function Legend({ backtest, live, rasterLabel, exposure }) {
  return (
    <div className="legend">
      <div className="legend-title">Debris-flow probability</div>
      <div className="legend-row"><span className="swatch" style={{ background: TIER.High }} /> High (&gt; 60%)</div>
      <div className="legend-row"><span className="swatch" style={{ background: TIER.Moderate }} /> Moderate (30–60%)</div>
      <div className="legend-row"><span className="swatch" style={{ background: TIER.Low }} /> Low (&lt; 30%)</div>
      {!live && <div className="legend-row"><span className="swatch swatch-line" style={{ borderColor: "#ffcc00" }} /> Fire perimeter (AOI)</div>}
      {rasterLabel && <div className="legend-row"><span className="swatch" style={{ background: "linear-gradient(90deg,#1a9850,#fee08b,#d73027)" }} /> {rasterLabel}</div>}
      {backtest && <div className="legend-row"><span className="swatch swatch-dashed" /> Actual 2018 debris-flow footprint</div>}
      {exposure && (
        <>
          <div className="legend-row"><span className="swatch" style={{ background: "#2171b5" }} /> Settlements downstream (people)</div>
          <div className="legend-row"><span className="swatch" style={{ background: "#1e90ff", height: "3px" }} /> Rivers downstream</div>
          {exposure.roads_tile_url && <div className="legend-row"><span className="swatch" style={{ background: "#ffd400" }} /> Roads downstream</div>}
        </>
      )}
      <div className="legend-note">
        {live ? "Basins filled by live modeled probability (real Earth Engine covariates)." : "Per drainage segment. Line color = modeled likelihood at the selected I15."}
      </div>
    </div>
  );
}

export default function MapView({
  perimeter, likelihood, inundation, bounds, backtest,
  live, rasterTileUrl, rasterLabel, showBasins, basins, basinProbs, highlightBasins,
  exposure,
}) {
  const mapRef = useRef(null);
  const rasterRef = useRef({ url: null, layer: null });
  const basinsRef = useRef({ key: null, layer: null });
  const vectorRef = useRef({ perimeter: null, likelihood: null, inundation: null });
  const expoRef = useRef({ key: null, layers: [] });

  // init once
  useEffect(() => {
    if (mapRef.current) return;
    const map = L.map("map", { zoomControl: true }).setView([34.45, -119.63], 12);
    L.tileLayer(BASEMAP_URL, { attribution: BASEMAP_ATTR, maxZoom: 18 }).addTo(map);
    mapRef.current = map;
  }, []);

  // raster tile layer (burn severity / pre / post) — recreated ONLY when the URL
  // changes, so playback frames never reload it (this was the "flashing" bug).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const r = rasterRef.current;
    if (r.url === rasterTileUrl) return;
    if (r.layer) { map.removeLayer(r.layer); r.layer = null; }
    if (rasterTileUrl) {
      r.layer = L.tileLayer(rasterTileUrl, { opacity: 0.75, attribution: "Sentinel-2 / Earth Engine" }).addTo(map);
    }
    r.url = rasterTileUrl;
  }, [rasterTileUrl]);

  // basin polygons — created when the basin SET changes; per-frame we only
  // restyle (fast, no teardown, no flashing).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const b = basinsRef.current;
    const key = showBasins && basins ? basins.map((x) => x.name).join(",") : null;
    if (b.key !== key) {
      if (b.layer) { map.removeLayer(b.layer); b.layer = null; }
      if (key) {
        const fc = {
          type: "FeatureCollection",
          features: basins.map((x) => ({
            type: "Feature",
            properties: { name: x.name, prob: basinProbs ? basinProbs[x.name] : null, dnbr: x.dnbr, T: x.T, S: x.S, threshold: x.threshold_i15_mm_per_hr },
            geometry: x.geometry,
          })),
        };
        b.layer = L.geoJSON(fc, {
          style: (f) => basinFill(f.properties.prob, highlightBasins),
          onEachFeature: (f, layer) => layer.bindPopup(basinPopup(f.properties)),
        }).addTo(map);
      }
      b.key = key;
    } else if (b.layer) {
      // same basins, new probabilities → restyle in place
      b.layer.eachLayer((lyr) => {
        const nm = lyr.feature.properties.name;
        const prob = basinProbs ? basinProbs[nm] : null;
        lyr.feature.properties.prob = prob;
        lyr.setStyle(basinFill(prob, highlightBasins));
      });
    }
  }, [showBasins, basins, basinProbs, highlightBasins]);

  // non-live vector layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const v = vectorRef.current;
    for (const k of Object.keys(v)) { if (v[k]) { map.removeLayer(v[k]); v[k] = null; } }
    if (!live) {
      if (perimeter) v.perimeter = L.geoJSON(perimeter, { style: perimeterStyle }).addTo(map);
      if (likelihood) v.likelihood = L.geoJSON(likelihood, { style: segmentStyle, onEachFeature: (f, l) => l.bindPopup(segPopup(f.properties || {})) }).addTo(map);
      if (backtest && inundation) v.inundation = L.geoJSON(inundation, { style: inundationStyle }).addTo(map);
    }
  }, [live, perimeter, likelihood, inundation, backtest]);

  // exposure highlight layers (settlements, roads, rivers, facilities in the runout zone)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const e = expoRef.current;
    const key = exposure ? `${exposure.lat},${exposure.lon}` : null;
    if (e.key === key) return;
    e.layers.forEach((l) => map.removeLayer(l));
    e.layers = [];
    if (exposure) {
      if (exposure.roads_tile_url)
        e.layers.push(L.tileLayer(exposure.roads_tile_url, { opacity: 0.55 }).addTo(map));
      if (exposure.people_tile_url)
        e.layers.push(L.tileLayer(exposure.people_tile_url, { opacity: 0.7, attribution: "WorldPop / GHSL" }).addTo(map));
      if (exposure.rivers_geojson)
        e.layers.push(L.geoJSON(exposure.rivers_geojson, { style: { color: "#1e90ff", weight: 2.5 } })
          .bindPopup("River reach downstream").addTo(map));
      (exposure.facilities || []).forEach((fac) => {
        e.layers.push(L.circleMarker([fac.lat, fac.lon], { radius: 5, color: "#fff", weight: 1, fillColor: "#e31a1c", fillOpacity: 1 })
          .bindPopup(`${fac.name} (${fac.type})`).addTo(map));
      });
    }
    e.key = key;
  }, [exposure]);

  // fit bounds when the framed data changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bounds || bounds.length !== 4) return;
    const [minLon, minLat, maxLon, maxLat] = bounds;
    map.fitBounds([[minLat, minLon], [maxLat, maxLon]], { padding: [40, 40] });
  }, [bounds && bounds.join(",")]);

  return (
    <div className="map-wrap">
      <div id="map" />
      <Legend backtest={backtest} live={live} rasterLabel={rasterLabel} exposure={exposure} />
    </div>
  );
}
