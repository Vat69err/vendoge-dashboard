# Vendoge Operations Dashboard

A Streamlit dashboard that reads live data straight from your Google Sheet
(no manual exports, no re-uploading files) and shows sales, refilling, and
stock-out trends across your machines.

This guide assumes you've never deployed a Streamlit app before. Follow it
top to bottom.

---

## 0. What you're working with

- `app.py` — the dashboard code
- `requirements.txt` — the Python packages Streamlit Cloud needs to install
- `.gitignore` — tells git which files to ignore

Because your Google Sheet is **public** ("Anyone with the link can view"),
the app reads it directly as a CSV export — no Google API keys, no service
account, no secrets file needed. This is the simplest possible setup.

---

## 1. Point the app at your sheet

Open `app.py` and find this line near the top:

```python
SHEET_ID = "PASTE_YOUR_GOOGLE_SHEET_ID_HERE"
```

Your Sheet ID is the long string in your sheet's URL:

```
https://docs.google.com/spreadsheets/d/  1AbCxyz123_THIS_IS_YOUR_ID  /edit
```

Copy that middle part and paste it in, e.g.:

```python
SHEET_ID = "1AbCxyz123_THIS_IS_YOUR_ID"
```

**Important:** the app expects your tabs to be named exactly:
- `Machine Wise Sales`
- `Consolidated Refilling`
- `Out of Stock Log`

If your real tab names differ even slightly (extra space, different
capitalization), update the `TABS` dictionary right below `SHEET_ID` to
match.

---

## 2. Run it locally first (recommended before deploying)

Open a terminal in this folder and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

This opens the dashboard in your browser at `http://localhost:8501`. Fix
anything that looks wrong here before deploying — it's much faster to
debug locally than on the cloud.

If you get an error loading the sheet, check:
- Is `SHEET_ID` actually pasted in (not left as the placeholder)?
- Is the sheet really shared as "Anyone with the link → Viewer"? (Share
  button, top-right of Google Sheets)
- Do the tab names match exactly?

---

## 3. Push the code to GitHub

If you don't already have a GitHub account, create one at
[github.com](https://github.com).

Then, from inside this project folder:

```bash
git init
git add .
git commit -m "Initial Vendoge dashboard"
```

Now create a new (empty) repository on GitHub:
1. Go to github.com → click the **+** in the top right → **New repository**
2. Name it something like `vendoge-dashboard`
3. Leave it empty (don't add a README there — you already have one)
4. Click **Create repository**

GitHub will show you commands like these — run them:

```bash
git remote add origin https://github.com/YOUR_USERNAME/vendoge-dashboard.git
git branch -M main
git push -u origin main
```

Refresh the GitHub page — your files should now be there.

---

## 4. Deploy on Streamlit Community Cloud (free)

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account (this also grants Streamlit permission
   to read your repos)
3. Click **Create app** → **From an existing repo**
4. Pick:
   - **Repository:** `YOUR_USERNAME/vendoge-dashboard`
   - **Branch:** `main`
   - **Main file path:** `app.py`
5. Click **Deploy**

It'll install your `requirements.txt` and launch the app. First deploy
usually takes 1–2 minutes. You'll get a public URL like:

```
https://vendoge-dashboard-yourname.streamlit.app
```

Share that link with anyone — Armaan, Bilawal, whoever — they don't need a
Streamlit or Google account to view it.

---

## 5. Keeping the data fresh

The app caches the Google Sheet data for **5 minutes** at a time (you'll
see this in the code as `ttl=300` on the `@st.cache_data` line in
`app.py`). That means:
- New rows added to your sheet show up within 5 minutes automatically, or
- Click the **"🔄 Refresh data now"** button in the sidebar to force an
  immediate reload.

If you want a longer or shorter refresh window, change `ttl=300` to
whatever number of seconds you prefer.

---

## 6. Updating the dashboard later

Any time you want to change something in `app.py` (add a chart, change a
color, add a filter):

```bash
git add .
git commit -m "describe what you changed"
git push
```

Streamlit Cloud automatically redeploys within a minute of the push — no
manual redeploy step needed.

---

## What's in the dashboard

- **Sidebar:** date range picker, machine filter, manual refresh button
- **KPI row:** total sales, units sold, average daily sales, cash share,
  stock-out count — all respect the filters above
- **Overview tab:** daily sales trend, machine split, top products, sales
  by category
- **Machine Sales tab:** brand/category filters, per-machine trend lines,
  cash vs. cashless breakdown, full product-level table
- **Refilling tab:** refill value by refiller, units refilled per day,
  full refill log
- **Stock-Outs tab:** events per day per machine, most frequently
  out-of-stock products, cash vs. cashless stock-out split, full log

---

## If something breaks on Streamlit Cloud

Click **Manage app** (bottom right of the deployed app) → it opens a log
panel. The error message there will usually point to a missing package
(add it to `requirements.txt`) or a data issue (check sheet tab names and
sharing settings, per Step 1).
