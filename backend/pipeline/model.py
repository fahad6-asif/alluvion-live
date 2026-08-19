"""
Staley et al. (2017) M1 post-fire debris-flow LIKELIHOOD model.

  Staley, D.M., Negri, J.A., Kean, J.W., Laber, J.L., Tillery, A.C., Youberg, A.M.,
  2017. "Prediction of spatially explicit rainfall intensity-duration thresholds
  for post-fire debris-flow generation." Geomorphology 278, 149-162.

--------------------------------------------------------------------------------
IMPORTANT — scope note (see build brief section 3):
--------------------------------------------------------------------------------
The PRODUCTION engine for this app is the official USGS `pfdf` library, which
delineates the stream-segment network from a DEM, computes the T/F/S covariates
from real burn-severity / soil / terrain rasters, and runs this exact regression
internally. See pipeline/pfdf_engine.py.

`pfdf` requires GDAL / rasterio / geopandas (a heavy geospatial C stack). When
that stack — or the live preset rasters — are unavailable (e.g. an offline demo,
or a machine without GDAL), the app falls back to synthetic seed data
(scripts/seed_preset_data.py) whose stream segments carry PRE-BAKED T/F/S
covariates. This module then applies the *published* Staley M1 link function in
closed form to those covariates to produce a per-segment probability at a given
rainfall intensity.

This is NOT a re-training or re-derivation of the model — it is the same
published equation with published coefficients, applied to covariates. It exists
so the demo is monotonic, honest, and runnable with no GDAL. Anything returned
this way is flagged `synthetic: true` all the way to the UI.
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# --- Published M1 coefficients, 15-minute duration -------------------------------
# logit(P) = B + Ct*(T*R) + Cf*(F*R) + Cs*(S*R)
#   T = proportion of upslope area that burned at moderate-or-high severity
#       AND has gradient >= 23 degrees              (dimensionless, 0..1)
#   F = mean catchment dNBR / 1000                  (dimensionless)
#   S = mean catchment soil KF-factor (erodibility) (dimensionless)
#   R = PEAK 15-MINUTE RAINFALL ACCUMULATION (mm)   <-- accumulation, NOT rate
M1_INTERCEPT = -3.63
M1_C_TERRAIN = 0.41
M1_C_FIRE = 0.67
M1_C_SOIL = 0.70

# The UI/API speak in I15 = peak 15-minute rainfall INTENSITY (mm/hr), because
# that is the quantity everyone quotes for these storms. The model wants the
# 15-minute ACCUMULATION (mm). 15 min = 1/4 hr, so:  accumulation = I15 / 4.
# Sanity: the "0.25 in in 15 min" design storm = 6.35 mm accumulation
#         -> 6.35 * 4 = 25.4 mm/hr ~= the "24 mm/hr" design storm everyone cites.
MINUTES_PER_I15_WINDOW = 15.0


def i15_mm_per_hr_to_accumulation_mm(i15_mm_per_hr: float) -> float:
    """Convert a peak 15-minute *intensity* (mm/hr) to a 15-minute *accumulation* (mm)."""
    return i15_mm_per_hr * (MINUTES_PER_I15_WINDOW / 60.0)


@dataclass(frozen=True)
class Covariates:
    """Per-segment model covariates (the T/F/S that pfdf would compute from rasters)."""
    T: float  # terrain: steep-and-burned proportion, 0..1
    F: float  # fire: mean dNBR / 1000
    S: float  # soil: mean KF-factor


def likelihood(cov: Covariates, i15_mm_per_hr: float) -> float:
    """
    Probability (0..1) of a debris flow for one segment at the given design storm.

    Applies the published Staley M1 logistic link. Monotonic increasing in I15.
    """
    r = i15_mm_per_hr_to_accumulation_mm(i15_mm_per_hr)
    x = (
        M1_INTERCEPT
        + M1_C_TERRAIN * cov.T * r
        + M1_C_FIRE * cov.F * r
        + M1_C_SOIL * cov.S * r
    )
    # numerically-stable logistic
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


# --- Probability tiers / colors (build brief section 5.5, fixed values) ----------
TIER_LOW = "Low"
TIER_MODERATE = "Moderate"
TIER_HIGH = "High"

TIER_COLORS = {
    TIER_LOW: "#2ca25f",       # green   (< 0.3)
    TIER_MODERATE: "#ff9900",  # orange  (0.3 - 0.6)
    TIER_HIGH: "#e31a1c",      # red     (> 0.6)
}

HIGH_THRESHOLD = 0.6
MODERATE_THRESHOLD = 0.3


def tier_for(p: float) -> str:
    if p > HIGH_THRESHOLD:
        return TIER_HIGH
    if p >= MODERATE_THRESHOLD:
        return TIER_MODERATE
    return TIER_LOW


def color_for(p: float) -> str:
    return TIER_COLORS[tier_for(p)]
