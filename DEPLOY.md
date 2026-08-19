# Deploying Alluvion Live — beginner, click-by-click

You are going to end up with **one public web link** to send your manager. Nobody logs
in to use it. The only "login" is a secret key your *server* uses to talk to Google — set
up once, never expires.

Two free services do the work:

- **Render** runs the Python **backend** (the part that talks to Google Earth Engine).
- **Vercel** hosts the **frontend** (the map/website) — this gives you the link you share.

You'll do it in 4 stages. Take them in order.

```
[ Stage 1 ]  Get a Google Earth Engine key  ->  you download ONE .json file
[ Stage 2 ]  Put this code on GitHub         ->  Render & Vercel read from there
[ Stage 3 ]  Deploy the backend on Render    ->  you get a backend URL
[ Stage 4 ]  Deploy the frontend on Vercel   ->  you get THE link to share
```

---

## Stage 1 — Get your Google Earth Engine key (the important part)

**What you're doing and why:** Google Earth Engine (GEE) won't give out satellite data to
just anyone — the server has to prove who it is. A **service account** is a "robot" Google
identity made for servers. It comes as a **single `.json` file** (the key). Your server
reads that key and is authenticated forever. Unlike `earthengine authenticate` (a personal
browser login that expires and disappears when the server restarts), **this key does not
expire** — that's what fixes the "it keeps reverting" problem for good.

Do this once, in your browser:

1. **Make/pick a Google Cloud project**
   - Go to https://console.cloud.google.com/
   - Top bar → project dropdown → **New Project** → name it e.g. `alluvion` → **Create**.
   - Make sure that project is selected (shown in the top bar) for every step below.

2. **Turn on the Earth Engine API for the project**
   - Go to https://console.cloud.google.com/apis/library/earthengine.googleapis.com
   - Click **Enable**.

3. **Register the project for Earth Engine** (one-time approval)
   - Go to https://code.earthengine.google.com/
   - If it asks you to register/choose a project, pick the project from step 1.
   - If you don't have Earth Engine access yet, sign up at
     https://earthengine.google.com/signup/ (non-commercial is usually approved quickly).

4. **Create the service account**
   - Go to https://console.cloud.google.com/iam-admin/serviceaccounts
   - **Create Service Account** → name it e.g. `alluvion-ee` → **Create and Continue** →
     you can skip the optional "grant roles" step → **Done**.
   - You'll now see it listed with an email like
     `alluvion-ee@alluvion.iam.gserviceaccount.com` — **copy that email**, you'll need it once.

5. **Download the JSON key**
   - Click the service account → **Keys** tab → **Add Key** → **Create new key** →
     **JSON** → **Create**.
   - A `.json` file downloads to your computer. **This is your key. Keep it private** — treat
     it like a password. (Do not email it, do not commit it to GitHub.)

6. **Let that service account use Earth Engine**
   - Go to https://code.earthengine.google.com/register (or
     https://signup.earthengine.google.com/#!/service_accounts)
   - Paste the service-account **email** from step 4 and register it. If your project is
     already Earth-Engine-registered (step 3), accounts in it are usually authorized
     automatically — this step just makes sure.

✅ **End of Stage 1:** you have one `.json` file on your computer. That's the whole key.

---

## Stage 2 — Put this code on GitHub

Render and Vercel both deploy *from a GitHub repository*. So the `alluvion-live` folder needs
to live in a GitHub repo.

- Easiest: ask me (Claude) to do this step — I can create the repo and push for you.
- Or do it yourself:
  1. Create an empty repo at https://github.com/new (e.g. `alluvion-live`), **Private** is fine.
  2. In a terminal, from inside the `alluvion-live` folder:
     ```bash
     git init
     git add .
     git commit -m "Alluvion Live"
     git branch -M main
     git remote add origin https://github.com/<your-username>/alluvion-live.git
     git push -u origin main
     ```

> The `.gitignore` already blocks your `.json` key and `node_modules` from being uploaded.
> **Never** put the key file inside the repo.

---

## Stage 3 — Deploy the backend on Render (free)

1. Go to https://render.com/ → sign up / log in **with GitHub**.
2. **New +** → **Web Service** → connect the `alluvion-live` repo.
3. Fill in:
   - **Root Directory:** `backend`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** **Free**
4. **Add your key as an environment variable** (this is where the `.json` goes — into a
   setting, never into the code):
   - Scroll to **Environment** → **Add Environment Variable**.
   - **Key:** `EE_SERVICE_ACCOUNT_JSON`
   - **Value:** open your `.json` key file in a text editor, **copy everything** (the whole
     `{ ... }`), and paste it as the value.
   - (Optional) `GEMINI_API_KEY` = a Google Gemini key, only if you want AI-written advisories
     instead of the built-in template. Skip it otherwise.
5. **Create Web Service.** Wait for the build to finish (a few minutes).
6. When it's live, copy the URL at the top, e.g. `https://alluvion-backend.onrender.com`.
7. **Test it:** open `https://alluvion-backend.onrender.com/api/live/status` in your browser.
   You want to see `"available": true`. If it says `false`, the key isn't right — recheck
   Stage 1 steps 5–6 and that you pasted the full JSON.

> **Free-tier note:** Render's free service goes to sleep after ~15 min of no visitors and
> takes ~50 seconds to wake up on the next visit. So the *first* load after a quiet period is
> slow, then it's fast. Mention this to your manager so a slow first open isn't mistaken for a
> bug.

---

## Stage 4 — Deploy the frontend on Vercel (free) → your shareable link

1. Go to https://vercel.com/ → sign up / log in **with GitHub**.
2. **Add New… → Project** → import the same `alluvion-live` repo.
3. Fill in:
   - **Root Directory:** `frontend`  *(click Edit and choose the `frontend` folder)*
   - **Framework Preset:** Vite (it should auto-detect).
4. **Add one environment variable** (this tells the website where its backend is):
   - **Name:** `VITE_API_BASE`
   - **Value:** the Render URL from Stage 3, e.g. `https://alluvion-backend.onrender.com`
     (no trailing slash).
5. **Deploy.** After a minute you get a link like `https://alluvion-live.vercel.app`.
6. Open it. You should see the map with the 3 tabs (Live hindcast / Scan / Forecast) loading
   real data. **That Vercel link is what you send your manager.** 🎉

> If instead you see the "Live satellite mode is not connected" screen: the frontend reached
> the backend but the backend isn't authenticated — fix the `EE_SERVICE_ACCOUNT_JSON` on
> Render (Stage 3, step 4/7). If it can't reach the backend at all, double-check `VITE_API_BASE`
> is the exact Render URL.

---

## Quick troubleshooting

| What you see | What it means | Fix |
|---|---|---|
| `"available": false` at `/api/live/status` | Backend can't authenticate to GEE | Recheck the pasted JSON key + Stage 1 steps 3–6 |
| "not connected" screen on the website | Frontend reached backend, but GEE not authed | Fix the Render key (above) |
| Website error "Cannot reach the backend" | `VITE_API_BASE` wrong or backend down | Set `VITE_API_BASE` to the exact Render URL; check Render is live |
| First load takes ~50s | Render free tier was asleep | Normal; it wakes up and is then fast |

## Updating later
Push a change to the GitHub repo → Render and Vercel **auto-redeploy**. Your key stays set;
you never re-authenticate.
