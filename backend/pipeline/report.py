"""
AI advisory report generator — the reasoning/writing layer (Gemini).

The DATA already determines the outcome (occurrence from the Staley model; per-
category risk from exposure). Gemini's job is NOT to decide — it is to bring the
numbers + a real satellite image of the area together and write a clear, human-
readable warning, with reasons for each statement. This keeps the facts locked in
code (no numeric hallucination) while the model does the narrative it's good at.

Gemini is multimodal: we pass the true-color satellite PNG of the area alongside the
numbers so it can describe where the hazard sits relative to settlements and rivers.
Gated behind GEMINI_API_KEY; a structured template produces the same report shape
when no key is set.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request

GEMINI_MODEL = "gemini-1.5-flash"
OCCURRENCE_REPORT_THRESHOLD = 0.50   # only generate a report above this occurrence prob

HONESTY_FOOTER = (
    "This is an experimental decision-support advisory generated from satellite and "
    "model data (USGS Staley-2017). It targets where to act with lead time — it does "
    "not prevent debris flows, predict exact timing, or replace official warnings "
    "(USGS, NWS, local emergency management)."
)

CATEGORY_ORDER = ["people_property", "infrastructure", "waterways", "farmland"]


def gemini_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def severity(occurrence: float, overall_risk: float) -> str:
    if occurrence >= 0.6 and overall_risk >= 0.6:
        return "CRITICAL"
    if occurrence >= 0.6 or overall_risk >= 0.5:
        return "HIGH"
    if occurrence >= OCCURRENCE_REPORT_THRESHOLD:
        return "ELEVATED"
    return "LOW"


def _pct(x):
    return f"{round((x or 0) * 100)}%"


def _fetch_image_b64(url: str):
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            return base64.b64encode(r.read()).decode()
    except Exception:
        return None


def _gemini(context: dict) -> str | None:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None
    occ = context.get("occurrence", 0)
    cats = {k: {**v, "risk_pct": _pct(occ * (v.get("factor") or 0))}
            for k, v in (context.get("risk_categories") or {}).items()}
    bbox = context.get("aoi_bbox")
    storm = context.get("storm", {})

    prompt = (
        "You are writing a post-fire debris-flow (mudslide) WARNING for the public and "
        "emergency managers. The numbers below are already computed and CORRECT — use "
        "them exactly, never invent or change a figure. A real true-color satellite image "
        "of the area is attached; use it only to DESCRIBE the scene (where steep burned "
        "slopes sit relative to the town, river, and fields) — do not count anything from it.\n\n"
        "Write a clear, simple report with these sections:\n"
        "1) HEADING: a one-line warning naming the severity and the area. Identify the place "
        f"from the coordinates/bounding box if you can ({bbox}); if you cannot identify it "
        "confidently, just refer to the coordinates — do not guess a place name.\n"
        "2) WHAT'S HAPPENING: frame it as 'Because the forecast/observed rainfall shows "
        "<the storm>, there is a <occurrence>% chance a debris flow occurs on the burned "
        "slopes above.' Give the reason (burn severity + steep slope + rainfall).\n"
        "3) WHAT IS THREATENED — go category by category (People & property, Roads & "
        "facilities, Waterways & ecosystem, Farmland & crops). For EACH, state its damage "
        "chance (the risk_pct) and, in one line, WHY / what specifically is at stake. "
        "Explicitly cover sediment impact on rivers/aquatic life/water supply, and crop "
        "burial for farmland.\n"
        "4) RECOMMENDED ACTIONS: concrete, prioritized, with lead-time framing.\n"
        "Keep it factual and bounded. Give a reason for each claim. End with the disclaimer.\n\n"
        f"DATA:\n{json.dumps({'severity': severity(occ, context.get('overall_risk', 0)), 'location': context.get('location'), 'fire': context.get('fire_name'), 'occurrence_pct': _pct(occ), 'storm': storm, 'categories': cats, 'metrics': context.get('exposure_metrics')}, indent=2)}\n\n"
        f"DISCLAIMER: {HONESTY_FOOTER}"
    )

    parts = [{"text": prompt}]
    img_b64 = _fetch_image_b64(context.get("satellite_thumb_url")) if context.get("satellite_thumb_url") else None
    if img_b64:
        parts.append({"inline_data": {"mime_type": "image/png", "data": img_b64}})

    body = json.dumps({"contents": [{"parts": parts}]}).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read())
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if HONESTY_FOOTER[:30] not in text:
            text += "\n\n" + HONESTY_FOOTER
        return text or None
    except Exception:
        return None


def _template(context: dict) -> str:
    occ = context.get("occurrence", 0)
    risk = context.get("overall_risk", 0)
    sev = severity(occ, risk)
    cats = context.get("risk_categories", {})
    fire = context.get("fire_name", "the burned area")
    loc = context.get("location", "")
    storm = context.get("storm", {})
    bbox = context.get("aoi_bbox")
    src = storm.get("source", "the rainfall")
    when = storm.get("peak_time_label") or storm.get("peak_time") or "the storm"

    lines = [
        f"⚠ DEBRIS-FLOW WARNING — {sev} — {fire} ({loc})",
        f"HIGH-RISK AREA: the burned slopes and their runout within {bbox} (lon/lat). "
        "Place identification from coordinates alone is approximate — confirm against a map.",
        f"WHAT'S HAPPENING: Because {src} shows a storm peaking around {when} "
        f"({storm.get('peak_i15','?')} mm/hr est. intensity), there is a {_pct(occ)} chance a "
        f"debris flow occurs on the burned slopes above. Reason: severe burn + steep terrain "
        f"(≥23°) + intense rain, via the USGS Staley-2017 model.",
        "WHAT IS THREATENED (chance of damage, and why):",
    ]
    for k in CATEGORY_ORDER:
        c = cats.get(k)
        if not c:
            continue
        cat_risk = occ * (c.get("factor") or 0)
        lines.append(f"  • {c['label']}: {_pct(cat_risk)} — {c.get('detail','')}. "
                     f"(Chance = {_pct(occ)} occurrence × exposure here.)")
    lines.append(
        "RECOMMENDED ACTIONS: Before the rain — issue evacuation warnings for the flagged "
        "runout zones, close creek-crossing roads, and ready debris basins. Alert downstream "
        "water and habitat managers to sediment risk to rivers; notify farm operators of "
        "burial risk to cropland. Re-check as new rainfall data arrives."
    )
    lines.append(HONESTY_FOOTER)
    return "\n\n".join(lines)


def generate(context: dict) -> dict:
    occ = context.get("occurrence", 0) or 0
    risk = context.get("overall_risk", 0) or 0
    above = occ >= OCCURRENCE_REPORT_THRESHOLD
    sev = severity(occ, risk)
    if not above:
        return {"text": None, "source": None, "severity": sev, "above_threshold": False,
                "threshold": OCCURRENCE_REPORT_THRESHOLD,
                "message": (f"Occurrence probability {_pct(occ)} is below the {_pct(OCCURRENCE_REPORT_THRESHOLD)} "
                            "reporting threshold — no advisory generated.")}
    if gemini_available():
        text = _gemini(context)
        if text:
            return {"text": text, "source": "gemini", "severity": sev, "above_threshold": True,
                    "used_image": bool(context.get("satellite_thumb_url"))}
    return {"text": _template(context), "source": "template", "severity": sev, "above_threshold": True}
