// Thin API client. In dev, Vite proxies /api -> backend (see vite.config.js).
// In production on Vercel, VITE_API_BASE points straight at the Render backend URL.
const BASE = import.meta.env.VITE_API_BASE || "";

// Surface FastAPI's {"detail": ...} message so errors are actionable, not just codes.
async function errorFrom(r) {
  let detail = `${r.status}`;
  try {
    const j = await r.json();
    if (j && j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
  } catch { /* non-JSON body */ }
  return new Error(detail);
}

async function jget(path) {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw await errorFrom(r);
  return r.json();
}
async function jpost(path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw await errorFrom(r);
  return r.json();
}

// Live-only API surface (no synthetic assess/backtest/fires/advisory endpoints).
export const api = {
  health: () => jget("/api/health"),
  liveStatus: () => jget("/api/live/status"),
  liveReplay: () => jget("/api/live/replay"),
  scan: (body) => jpost("/api/scan", body),
  forecastStatus: () => jget("/api/forecast/status"),
  forecast: (body) => jpost("/api/forecast", body),
  exposure: (body) => jpost("/api/exposure", body),
  reportStatus: () => jget("/api/report/status"),
  report: (body) => jpost("/api/report", body),
};
