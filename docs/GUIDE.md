# Alluvion Guide

This guide explains how Alluvion works. It is written in plain language. You do not need to know anything about satellites, debris flows or machine learning.

Back to the [README](../README.md). To run or deploy the app, see [DEPLOY.md](DEPLOY.md).

## Contents

1. [What Alluvion is](#1-what-alluvion-is)
2. [The problem: post-fire debris flows](#2-the-problem-post-fire-debris-flows)
3. [How one scan works, step by step](#3-how-one-scan-works-step-by-step)
4. [The science: the USGS equation](#4-the-science-the-usgs-equation)
5. [Where the data comes from](#5-where-the-data-comes-from)
6. [The three tabs](#6-the-three-tabs)
7. [Occurrence and risk](#7-occurrence-and-risk)
8. [The advisory report](#8-the-advisory-report)
9. [The backend API](#9-the-backend-api)
10. [What is real and what is estimated](#10-what-is-real-and-what-is-estimated)
11. [Limits](#11-limits)
12. [Questions and answers](#12-questions-and-answers)
13. [Known issues](#13-known-issues)
14. [Ideas for later](#14-ideas-for-later)

---

## 1. What Alluvion is

When a wildfire burns a hillside, the next heavy rain can turn that hillside into a **debris flow**. This is a fast river of mud, rock and water. It can bury homes, roads and rivers below.

Alluvion is a tool that:

* finds the burned area from satellite images,
* works out how likely a debris flow is during a storm,
* checks what is downstream (people, buildings, roads, rivers, farmland),
* and writes a short warning report.

Its goal is to show responders **where to look before the storm arrives**.

It is a targeting tool. It does not stop debris flows. It cannot predict the exact minute one starts. It is not an official safety system.

---

## 2. The problem: post-fire debris flows

Healthy plants and soil act like a sponge. They soak up rain and hold the hill together.

A fire burns the plants. It also bakes the soil so water runs off it instead of soaking in. Think of rain hitting a car park instead of a garden.

So on a **burned, steep** hill, heavy rain does not sink in. It rushes downhill and picks up ash, soil and rocks. That is a debris flow. Debris flows are:

* **Fast.** They can move faster than a person can run.
* **Strong.** They carry boulders and can destroy buildings.
* **Deadly.** On 9 January 2018, debris flows in Montecito, California killed 23 people and damaged or destroyed hundreds of homes. The Thomas Fire had burned the hills above the town a few weeks earlier.

A debris flow needs three things together:

1. a recent burn,
2. a steep slope,
3. intense rain.

We can measure the first two from space and watch the third with weather data. That is why a warning tool is possible.

The danger is highest in the first one or two rainy seasons after a fire. It then drops as plants grow back, usually over a few years.

---

## 3. How one scan works, step by step

This section follows the data through the system. For each step you can see where the data comes from, what it contains, and where it goes next.

**Step 1: The request arrives.**
The website sends a request to the backend. For a scan, it sends a latitude, a longitude and an approximate fire date. For the Montecito replay it sends nothing, because the place and dates are fixed.

**Step 2: The burn scar.**
* *Comes from:* Sentinel-2 satellite images (Landsat 8 for older dates), loaded from Google Earth Engine.
* *Contains:* a before-fire picture and an after-fire picture. Clouds are removed first.
* *What happens:* the app measures a "plant health" number (NBR) in both pictures and subtracts them. `dNBR = NBR before - NBR after`. Burned land gives a positive number. A bigger number means a worse burn.
* *Goes to:* the model, as the fire value **F** (dNBR divided by 1000), and to the terrain step, to find the burned area.

**Step 3: Terrain and soil.**
* *Comes from:* the SRTM elevation map and OpenLandMap soil data.
* *Contains:* the slope of the land in degrees, and the share of clay, sand and organic matter in the soil.
* *What happens:* the app marks ground steeper than 23 degrees. It combines this with the burn map to get **T**, the share of the hillside that is both steep and burned at moderate or high severity. It turns the soil data into a soil erodibility number **S** (the K-factor).
* *Goes to:* the model.

**Step 4: The rain.**
* *Comes from:* NASA GPM IMERG satellite rain, measured every 30 minutes. (In forecast mode it comes from a weather forecast instead.)
* *Contains:* how much rain fell in each half hour over the area.
* *What happens:* the app takes the strongest area average and multiplies it by 3 to estimate the peak 15-minute intensity, called **I15**. This is an estimate. Satellite rain is smoothed, so a short, sharp burst looks weaker than it was.
* *Goes to:* the model, as the rain value **R**.

**Step 5: The model.**
* *Comes from:* the numbers T, F, S and R above, for each drainage basin.
* *What happens:* the USGS Staley (2017) equation turns them into one probability between 0% and 100%. This is the **occurrence** probability. See the next section.
* *Goes to:* the map (basins are coloured by probability) and to the warning check.

**Step 6: Exposure.**
* *Comes from:* WorldPop (people), JRC GHSL (built-up land), US Census TIGER (roads), HydroSHEDS (rivers) and the USDA Cropland Data Layer (farmland).
* *What happens:* the app looks at the gentle valley floor below the burned slopes (ground flatter than 12 degrees). That is where debris spreads out and where people live. It counts what is there and turns each count into a 0 to 100% exposure factor.
* *Goes to:* the risk numbers and the advisory.

**Step 7: The warning check.**
If the occurrence probability is above 50%, the app can write an advisory. Below 50%, it does not.

**Step 8: The response.**
The backend sends everything back as one JSON answer. The website draws the map, the charts and the result cards.

---

## 4. The science: the USGS equation

Alluvion does not invent its own science. It uses the model that the US Geological Survey (USGS) uses for these warnings:

> Staley, D.M., et al. (2017). Prediction of spatially explicit rainfall intensity-duration thresholds for post-fire debris-flow generation. *Geomorphology*, 278, 149-162. (This is the "M1" model.)

The model is a logistic regression. It turns several inputs into a probability.

```
x = B + C1 * (T * R) + C2 * (F * R) + C3 * (S * R)

Probability = e^x / (1 + e^x)
```

The second line squeezes the result into a number between 0% and 100%.

| Symbol | Name | Meaning | Source in Alluvion |
|---|---|---|---|
| T | Terrain | Share of the upslope area that is steep (23 degrees or more) and burned at moderate or high severity | SRTM + burn map |
| F | Fire | Burn severity (dNBR divided by 1000) | Sentinel-2 |
| S | Soil | How easily the soil washes away (K-factor) | OpenLandMap |
| R | Rain | Peak 15-minute rain amount in mm | IMERG or a forecast |

The fixed numbers come from the published paper. The USGS found them using real past debris flows. Alluvion only applies the finished equation. It does not train or change it.

```
B  = -3.63
C1 =  0.41   (terrain)
C2 =  0.67   (fire)
C3 =  0.70   (soil)
```

**The key point:** rain (R) is multiplied into every term. It is not just one more ingredient. It is the amplifier on all the others.

* With no rain, the probability is close to zero, however burned or steep the land is.
* As rain grows, the probability climbs. It climbs faster on land that is more burned, steeper and easier to wash away.

**Why 15 minutes?** Debris flows are triggered by short, hard bursts of rain, not slow drizzle. The app talks about **I15**, the peak 15-minute intensity in mm per hour. The model needs the 15-minute amount in mm, which is `I15 / 4`. For example, the well-known trigger of 0.25 inch in 15 minutes is about 24 mm per hour.

---

## 5. Where the data comes from

Everything comes from Google Earth Engine, Google's online library of satellite and map data.

| What we need | Dataset | What it gives |
|---|---|---|
| Burn scar | Sentinel-2 (2016 and later) or Landsat 8 | Before and after pictures, so we can compute dNBR |
| Slope | SRTM | The shape of the land |
| Soil erodibility | OpenLandMap (clay, sand, organic matter), turned into a K-factor | How easily soil washes away |
| Rain that fell | GPM IMERG | Satellite rain every 30 minutes |
| Forecast rain | NOAA CFSv2 (2011 to now). WeatherNext if access is granted | Predicted rain |
| People | WorldPop (100 m grid) | People in the valley area |
| Buildings | JRC GHSL built-up surface | Built-up land in the valley area |
| Roads | US Census TIGER 2016 | Road length |
| Rivers | WWF HydroSHEDS | River reaches in the path |
| Farmland | USDA Cropland Data Layer | Cultivated land |
| Hospitals, schools, fire stations | Google Places (needs a key) | Critical buildings |
| Written advisory | Gemini (needs a key) | Readable report text |

---

## 6. The three tabs

### Tab 1: Live hindcast (Jan 2018 Montecito)

This replays a real disaster **blind**. The app only uses data from before 6 January 2018. It cannot cheat by knowing what happened.

1. **Detect the burn scar.** Step through the before-fire and after-fire satellite images, then the burn map.
2. **Play the storm.** The real rain of 8 to 9 January 2018 plays back every 30 minutes. You can change the speed.
3. **Watch the warnings.** A warning appears for each creek when its probability passes 50%.

The app covers five creeks: Montecito, San Ysidro, Buena Vista, Romero and Toro Canyon. In the current live run, four creeks are warned at 10:00 UTC and Montecito Creek at 10:30 UTC on 9 January. The app counts the flows as starting at 11:30 UTC. That is about 1 to 1.5 hours of warning.

Montecito Creek has the weakest burn in this run (dNBR 147) and the lowest probability (59%).

### Tab 2: Scan any US location

You type a latitude, longitude and an approximate fire date. Or you click a preset: Thomas Fire, Bobcat Fire, Grizzly Creek or El Dorado Fire.

The app then:

* finds the burn scar for that place and time,
* searches about 8 months after the fire for the strongest storm (or you can type storm dates),
* runs the model over the area and shows the result on the map.

This tab uses a grid of cells, not true drainage basins. It is a simpler version of the USGS method.

If there was no fire, the app says it found no significant burn.

### Tab 3: Forecast (experimental)

This uses a weather **forecast** instead of rain that already fell. You choose a source:

* **NOAA CFSv2.** Public. Works for dates back to 2011. It is coarse (about 22 km and 6 hours), so it smooths away short bursts.
* **Google WeatherNext.** Sharper, but it needs access from Google and only covers recent dates. It is switched off on the live demo.

This tab is marked **experimental**. Forecasting the peak 15-minute rain days ahead is very hard.

---

## 7. Occurrence and risk

These are two different ideas.

* **Occurrence** is the chance that a debris flow happens at all. It comes from the USGS equation. It does not care whether anyone lives nearby.
* **Risk** is the chance that a debris flow hurts something. In Alluvion: `risk = occurrence x exposure factor`.

Why split them? A debris flow in empty wilderness has high occurrence but almost no risk to people. A debris flow above a town has high occurrence and high risk. If you merge them into one number, you lose that difference.

Alluvion shows four risk categories, each with its own exposure factor:

* **People and property.** From people and built-up land.
* **Roads and facilities.** From roads, and from hospitals, schools and fire stations if a Google Places key is set.
* **Waterways.** From rivers. Mud in a river harms fish and water supply even where nobody lives.
* **Farmland.** From cultivated land that debris could bury.

Counts are made in the valley area below the burned slopes. Things closer to the burn count more. The counts are turned into 0 to 100% factors with a smooth curve, so a normal town lands in a believable middle range instead of always hitting 100%.

---

## 8. The advisory report

This is the "agent" part of Alluvion. It runs in three steps.

**Step 1: The threshold.** A report is only made if the occurrence probability is above **50%**. A small chance of a mudslide should not create a panic warning.

**Step 2: The writing.**
* If a `GEMINI_API_KEY` is set, Google Gemini writes the report. It receives the computed numbers and a satellite picture of the area.
* If there is no key, the app builds the report from a built-in template. **The live demo uses the template**, because no Gemini key is set on it.

Either way, the numbers come from the code. The AI only writes the words around them. It is told never to change a figure. The report has a heading, a "because" line explaining the storm, the damage chance for each category with a reason, and recommended actions.

**Step 3: The email.** A report can be emailed only if someone clicks send, types a recipient, and the server has Gmail details set. Nothing is ever sent on its own. Email is not set up on the live demo.

The report is always a draft for a human to read first. "Generate" and "Send" are two separate buttons.

---

## 9. The backend API

The backend is a FastAPI app. Interactive docs are at `/docs` on the backend address. All answers are JSON.

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Server status and whether Earth Engine is connected |
| GET | `/api/live/status` | Is the live hindcast available? |
| GET | `/api/live/replay` | The full blind Montecito replay. Cached, because Earth Engine is slow. Add `?force=true` to rebuild it. |
| POST | `/api/scan` | Scan any US location |
| GET | `/api/forecast/status` | Which forecast sources are available |
| POST | `/api/forecast` | Run the experimental forecast |
| POST | `/api/exposure` | Count what is downstream of a location |
| GET | `/api/report/status` | Is Gemini or email set up? |
| POST | `/api/report` | Generate (and optionally email) an advisory |

If Earth Engine is not connected, the live endpoints return error 503. The website then shows a "not connected" screen. There is no fake data in this version.

**Example: scan the Thomas Fire area**

```
POST /api/scan
{
  "lat": 34.46,
  "lon": -119.63,
  "fire_date": "2017-12-04",
  "radius_km": 6
}
```

`storm_start` and `storm_end` are optional. Without them, the app finds the strongest storm after the fire.

**Example: forecast**

```
POST /api/forecast
{
  "lat": 34.46,
  "lon": -119.63,
  "fire_date": "2017-12-04",
  "source": "cfsv2"
}
```

**Example: exposure**

```
POST /api/exposure
{ "lat": 34.46, "lon": -119.63, "radius_km": 6 }
```

---

## 10. What is real and what is estimated

**Real, from live data:**

* Burn scar from real Sentinel-2 and Landsat images.
* Slope from SRTM.
* Rain from GPM IMERG and forecasts from NOAA CFSv2.
* The USGS Staley (2017) equation and its published numbers.
* The exposure counts (people, buildings, roads, rivers, farmland).
* The Montecito replay, a blind run on a real event.

**Estimated or simplified (and labelled in the app):**

* The peak 15-minute rain (I15) is IMERG's area average multiplied by 3. It is not a rain gauge reading. For comparison, gauges measured a peak of roughly 78 to 105 mm per hour on 9 January 2018.
* Soil erodibility is a proxy made from soil composition. The USGS uses a different soil database.
* The Montecito basins are simple bands across the burned front, not true watersheds.
* The Scan tab uses a grid of cells instead of basins.
* The "valley area" is ground flatter than 12 degrees. It is not a flow simulation.
* The exposure factor is a designed formula. It is not a tested index.

---

## 11. Limits

* **US only.** The soil data covers only the United States.
* **Not validated.** It is a prototype. Do not use it for real safety decisions.
* **Coarse forecasts.** CFSv2 is about 22 km wide and averages over 6 hours. It cannot see a short, strong burst.
* **Satellite rain is late.** Satellite rain data arrives a few hours after it falls. Ground radar would be faster.
* **No fire detection.** You tell the app where and when. It does not watch for new fires.
* **No continuous monitoring.** It runs when you ask. It does not run in the background.
* **No time-since-fire factor.** The model does not lower the risk as a burn scar heals over the years.
* **Approximate place names.** The app labels areas by coordinates.

---

## 12. Questions and answers

**Does it detect fires by itself?**
No. You choose the place and date. It does detect the burn scar from satellite images once you point it at an area.

**How do rain, fire and soil combine?**
Rain multiplies all the others (section 4). Soil (0.70) and fire (0.67) have almost equal weight. Terrain (0.41) has a little less. In real life burn severity and slope change the most from place to place, so they often decide which valley is worst.

**What happens on flat land?**
The terrain term needs slopes of 23 degrees or more. Flat land has none, so the probability drops close to zero. That is correct, because debris flows need steep ground. Flat land might flood, but it will not produce a debris flow.

**How far ahead does it look?**
In Scan mode it searches about 8 months after the fire for the worst storm. That is not a forecast. Real forecast lead time is only a few days.

**Why is a forecast probability lower than the observed one for the same storm?**
The forecast model averages rain over a large area and several hours. It smooths away the short burst that causes debris flows. The forecast is too blurry to see it.

**If it is raining now but the forecast missed it, would it warn?**
A full operating version would. It would watch measured rain as well as forecasts, so the measured rain acts as a safety net. Alluvion today shows each path separately in its tabs. It does not run both together.

**Why does the first page load take so long?**
The backend runs on Render's free plan. It sleeps after about 15 minutes with no visitors and takes 30 to 60 seconds to wake up. See [DEPLOY.md](DEPLOY.md) for a fix.

---

## 13. Known issues

* **Cold start.** The first load after a quiet period is slow (see above).
* **Gemini is not on in the live demo.** No key is set, so advisories use the template. If you add a key and still get template text, check the model name in `backend/pipeline/report.py` (`GEMINI_MODEL`). It is set to `gemini-1.5-flash`, which may be out of date. Change it to a current Gemini model name.
* **WeatherNext is off.** It needs access from Google.
* **Email is off.** No Gmail details are set on the live demo.
* **Open API.** The API allows requests from any website (CORS is open). That is fine for a public read-only demo with no accounts. Do not add private data without changing it.
* **Earth Engine speed.** Some scans take several seconds because Earth Engine does the heavy work.

---

## 14. Ideas for later

If Alluvion became a real system, these changes would help most.

* **Automatic fire detection.** Watch a live fire feed (for example NASA FIRMS) and assess every new burn scar.
* **A continuous loop.** Detect fire, assess the hazard, check what is downstream, watch forecasts and measured rain, warn, and keep updating until the storm passes.
* **Real alerts.** Send warnings to the right people, with a human approving each one.
* **True watersheds.** Draw real drainage basins from the elevation map instead of simple bands.
* **A recovery factor.** Lower the risk as a burn scar heals.
* **Better rain data.** Ground radar for live rain, and sharper forecast models.
* **A test dashboard.** Replay many past disasters and report real accuracy numbers.
* **Richer exposure.** Add power, water supply and protected habitat.

What to remove or replace in that version: manual coordinate entry as the main path, the coarse CFSv2 forecast, and the simplified valley area.

Even a perfect version cannot stop debris flows, name the exact minute one starts, or forecast a small downpour days ahead. Its real value is turning hours or days of warning into targeted action for the specific places, people, rivers and farms in harm's way.

---

*Alluvion was designed, specified and directed by Fahad Asif. All of the code was written by Claude (Anthropic). Built on Google Earth Engine and the USGS Staley (2017) model. A targeting aid, not an operationally validated safety system. Always follow official sources.*
