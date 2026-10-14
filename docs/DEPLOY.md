# Deploying and Running Alluvion

This guide shows how to put Alluvion online, step by step, with clicks on websites. It also shows how to run it on your own computer.

Back to the [README](../README.md). To understand how the app works, read [GUIDE.md](GUIDE.md).

## Contents

1. [The plan](#the-plan)
2. [Stage 1: Get a Google Earth Engine key](#stage-1-get-a-google-earth-engine-key)
3. [Stage 2: Put the code on GitHub](#stage-2-put-the-code-on-github)
4. [Stage 3: Deploy the backend on Render](#stage-3-deploy-the-backend-on-render)
5. [Stage 4: Deploy the frontend on Vercel](#stage-4-deploy-the-frontend-on-vercel)
6. [Stage 5: Test it](#stage-5-test-it)
7. [Optional extras](#optional-extras)
8. [Fix the slow first load](#fix-the-slow-first-load)
9. [Updating later](#updating-later)
10. [Run it on your own computer](#run-it-on-your-own-computer)
11. [Settings reference](#settings-reference)
12. [Troubleshooting](#troubleshooting)

---

## The plan

Alluvion has two parts. Each one goes on a different free website.

* **Backend (Render).** The Python server. It talks to Google Earth Engine. It holds the secret key.
* **Frontend (Vercel).** The map website. This gives you the public link that you share.

You do it in five stages. Take them in order.

```
Stage 1   Get an Earth Engine key        -> you download one .json file
Stage 2   Put the code on GitHub         -> Render and Vercel read from there
Stage 3   Deploy the backend on Render   -> you get a backend address
Stage 4   Deploy the frontend on Vercel  -> you get the public link
Stage 5   Test it
```

Nobody has to log in to use the finished site. The only login is the secret key that your server uses to talk to Google. You set it up once and it does not expire.

---

## Stage 1: Get a Google Earth Engine key

**Why:** Google Earth Engine does not give satellite data to just anyone. The server has to prove who it is. A **service account** is a robot identity for servers. It comes as one `.json` file (the key). Unlike `earthengine authenticate`, which is a personal browser login that expires, this key does not expire.

Do this once, in your browser.

**1. Make or pick a Google Cloud project**
* Go to https://console.cloud.google.com/
* Click the project menu at the top, then **New Project**.
* Name it (for example `alluvion`) and click **Create**.
* Make sure that project is selected at the top for every step below.

**2. Turn on the Earth Engine API**
* Go to https://console.cloud.google.com/apis/library/earthengine.googleapis.com
* Click **Enable**.

**3. Register the project for Earth Engine**
* Go to https://code.earthengine.google.com/
* If it asks you to register, choose your project from step 1.
* If you do not have Earth Engine access yet, sign up at https://earthengine.google.com/signup/ (non-commercial use is usually approved quickly).

**4. Create the service account**
* Go to https://console.cloud.google.com/iam-admin/serviceaccounts
* Click **Create Service Account**.
* Give it a name (for example `alluvion-ee`).
* Click **Create and Continue**, skip the optional role step, then click **Done**.
* The account appears in the list with an email like `alluvion-ee@alluvion.iam.gserviceaccount.com`. Copy that email.

**5. Download the key**
* Click the service account, then open the **Keys** tab.
* Click **Add Key**, then **Create new key**, choose **JSON**, then **Create**.
* A `.json` file downloads to your computer. This is your key.

**Keep the key private.** Treat it like a password. Do not email it. Do not put it in GitHub. Do not paste it in chat.

**6. Let the account use Earth Engine**
* Go to https://code.earthengine.google.com/register (or https://signup.earthengine.google.com/#!/service_accounts).
* Paste the service-account email from step 4 and register it.
* If your project is already registered (step 3), the account is usually allowed already. This step just makes sure.

**End of Stage 1:** you have one `.json` file on your computer.

---

## Stage 2: Put the code on GitHub

Render and Vercel both deploy from a GitHub repository. So the project needs to live in one.

1. Go to https://github.com/new
2. Repository name: `alluvion-live` (or any name you like).
3. Choose **Public** or **Private**. Both work with Render and Vercel.
4. Click **Create repository**.
5. On the new empty repository page, click **uploading an existing file**.
6. Drag the project files and folders into the page: `backend`, `frontend`, `docs`, `README.md` and `.gitignore`.
7. Scroll down and click **Commit changes**.

The `.gitignore` file already blocks key files and `node_modules` from being uploaded. Still, **never put your key file inside the project folder**.

If you use Git on the command line, you can instead run this from the project folder:

```
git init
git add .
git commit -m "Alluvion"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/alluvion-live.git
git push -u origin main
```

---

## Stage 3: Deploy the backend on Render

1. Go to https://render.com/ and sign up or log in **with GitHub**.
2. Click **New +**, then **Web Service**.
3. Connect your `alluvion-live` repository.
4. Fill in the form:
   * **Name:** `alluvion-live` (this becomes part of your web address)
   * **Root Directory:** `backend`
   * **Runtime:** Python 3
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   * **Instance Type:** Free
5. Add your key as an environment variable. This is where the `.json` goes. It goes into a setting, never into the code.
   * Scroll to **Environment** and click **Add Environment Variable**.
   * **Key:** `EE_SERVICE_ACCOUNT_JSON`
   * **Value:** open your `.json` key file in a text editor, copy **everything** (the whole `{ ... }`), and paste it as the value.
6. Click **Create Web Service**. Wait for the build to finish (a few minutes).
7. When it is live, copy the address at the top. It looks like `https://alluvion-live.onrender.com`.
8. Test it. Open `https://alluvion-live.onrender.com/api/live/status` in your browser. You want to see `"available": true`.

If it says `false`, the key is not right. Check Stage 1 steps 3 to 6 and make sure you pasted the full JSON.

There is also a `backend/render.yaml` file. It is an optional shortcut that fills in the same values. You can use the form above instead.

---

## Stage 4: Deploy the frontend on Vercel

1. Go to https://vercel.com/ and sign up or log in **with GitHub**.
2. Click **Add New**, then **Project**.
3. Import the same `alluvion-live` repository.
4. Fill in the form:
   * **Root Directory:** click **Edit** and choose the `frontend` folder.
   * **Framework Preset:** Vite (it should be picked automatically).
5. Add one environment variable. This tells the website where its backend is.
   * **Name:** `VITE_API_BASE`
   * **Value:** your Render address from Stage 3, for example `https://alluvion-live.onrender.com`. Do not add a slash at the end.
6. Click **Deploy**. After about a minute you get a link like `https://alluvion-live.vercel.app`.

That Vercel link is the public link you share.

If you change `VITE_API_BASE` later, you must **redeploy** the project on Vercel. The value is baked in when the site is built.

---

## Stage 5: Test it

1. Open your Vercel link. If the page says "Connecting to Google Earth Engine", wait up to a minute. This is the free Render server waking up.
2. You should see the map with three tabs: Live hindcast, Scan any US location and Forecast.
3. On the first tab, click **Next** to step through the burn-scar images. Then press play to run the storm replay. Warnings should appear for the creeks.
4. On the second tab, click a preset (for example Thomas Fire) and click **Run live scan**.

If something is wrong, see [Troubleshooting](#troubleshooting).

---

## Optional extras

Each of these is a setting on **Render**. Go to your service, open **Environment**, add the variable, and save. Render restarts the server for you.

**AI-written advisories (Gemini).**
* Get a key from https://aistudio.google.com/
* Add `GEMINI_API_KEY` with your key.
* Without it, the app uses a built-in template for advisories.
* If you still get template text after adding a key, the model name in `backend/pipeline/report.py` (`GEMINI_MODEL`) may be out of date. Change it to a current Gemini model name.

**Email an advisory.**
* You need a Gmail account with 2-Step Verification on.
* Create an App Password at Google Account, Security, App passwords.
* Add `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`.
* The app only sends when a person clicks send and types a recipient.

**Hospitals, schools and fire stations.**
* Create a Google Maps Platform key with the Places API turned on.
* Add `GOOGLE_MAPS_API_KEY`.

**WeatherNext forecasts.**
* Open the WeatherNext dataset in the Earth Engine Data Catalog and click **Request access**. Approval can take several days.
* Once approved, add `ENABLE_WEATHERNEXT` with the value `true`.

---

## Fix the slow first load

Render's free plan puts the server to sleep after about 15 minutes with no visitors. The next visit takes 30 to 60 seconds to wake it up. This is normal, but it can look like a bug.

Options:

* **Do nothing,** and keep the note about the slow first load in your README. This is the free choice.
* **Use a free pinger.** A service such as UptimeRobot can open `https://YOUR-BACKEND/api/health` every 10 minutes. That keeps the server awake. Free plans have monthly hour limits, so check Render's current rules.
* **Pay for an always-on Render instance.** This removes the delay completely.

---

## Updating later

Push a change to your GitHub repository. Render and Vercel both **redeploy on their own**. Your key stays set. You never sign in again.

On GitHub, you can edit a file on the website with the pencil icon, or upload new files with **Add file**, then **Upload files**.

---

## Run it on your own computer

You need Python 3, Node.js, and a Google Cloud project that is registered for Earth Engine (Stage 1, steps 1 to 3).

**Backend** (first terminal). On Windows:

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
earthengine authenticate
set EE_PROJECT=your-google-cloud-project-id
uvicorn app.main:app --port 8000
```

On macOS or Linux, use `source .venv/bin/activate` and `export EE_PROJECT=your-google-cloud-project-id`.

`earthengine authenticate` opens a browser so you can log in once. Instead, you can use a service-account key: set `EE_SERVICE_ACCOUNT_JSON` to the whole content of the key file.

**Frontend** (second terminal):

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. In this mode the website sends `/api` requests to the backend on port 8000. To use a different backend address, set `VITE_BACKEND_URL` before `npm run dev`.

Check the backend by opening http://localhost:8000/api/live/status. You want `"available": true`. If it says `false`, Earth Engine sign-in did not work, and the website shows the "not connected" screen. That is on purpose. This version never shows fake data.

Keep both terminals open while you use the app.

---

## Settings reference

**Backend (Render or your computer):**

| Name | Required | What it does |
|---|---|---|
| `EE_SERVICE_ACCOUNT_JSON` | Yes, for deploying | The full service-account key JSON. The account email and project are read from inside it. |
| `EE_PROJECT` | Local sign-in only | Your Google Cloud project ID. It can also override the project in the key. |
| `GOOGLE_APPLICATION_CREDENTIALS` and `EE_SERVICE_ACCOUNT` | Alternative | A path to a key file on disk, and the account email. Use these instead of the JSON setting if you prefer a file. |
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | No | Gemini-written advisories |
| `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` | No | Email an advisory |
| `GOOGLE_MAPS_API_KEY` | No | Hospitals, schools and fire stations |
| `ENABLE_WEATHERNEXT` | No | Set to `true` once Google gives you access |

**Frontend (Vercel):**

| Name | Required | What it does |
|---|---|---|
| `VITE_API_BASE` | Yes, on Vercel | The backend address, with no slash at the end |
| `VITE_BACKEND_URL` | Local only | Where `npm run dev` sends `/api` requests. The default is `http://localhost:8000`. |

---

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| `"available": false` at `/api/live/status` | The backend cannot sign in to Earth Engine | Check the pasted JSON key and Stage 1 steps 3 to 6. Make sure you pasted the full JSON. |
| The page says "not connected" | The website reached the backend, but the backend is not signed in | Fix the key on Render, as above |
| "Connecting to Google Earth Engine" for a long time | The free Render server is waking up | Wait up to a minute, then reload |
| Error "Cannot reach the backend" | `VITE_API_BASE` is wrong, or the backend is down | Set `VITE_API_BASE` to the exact Render address (no slash). Redeploy on Vercel. Check Render is live. |
| Page is blank after changing a setting on Vercel | The site was not rebuilt | Redeploy the project on Vercel |
| Render build fails | A missing or wrong setting | Check that Root Directory is `backend` and the Build Command is `pip install -r requirements.txt` |
| Vercel build fails | A wrong root folder | Check that Root Directory is `frontend` |
| Advisory shows template text although a Gemini key is set | The model name is old, or the key is wrong | See "AI-written advisories" above |
| Need to see what went wrong on the backend | The logs have the real error | Open your service on Render and click **Logs**. If Earth Engine sign-in fails, the exact error is printed there. |

**If your key is ever leaked:** go to the Google Cloud service accounts page, open the account, open **Keys**, and delete the key. Then create a new one and update `EE_SERVICE_ACCOUNT_JSON` on Render.
