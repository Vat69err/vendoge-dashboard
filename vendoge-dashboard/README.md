# Vendoge Operations Dashboard

A Streamlit dashboard that reads live data straight from your Google Sheet
(no manual exports, no re-uploading files) and shows revenue, refilling, SKU
mix, and dispense-failure trends across your machines.

This guide assumes you've never deployed a Streamlit app before. Follow it
top to bottom.

---

## 0. What you're working with

- `app.py` — the dashboard code
- `requirements.txt` — the Python packages Streamlit Cloud needs to install
- `.gitignore` — tells git which files to ignore

Because your Google Sheet is **public** ("Anyone with the link can view"),
the app reads each tab directly as a CSV export by name — no Google API
keys, no service account, no gids to configure. This is the simplest
possible setup.

---

## 1. Point the app at your sheet

The app needs your Google Sheet's ID set up in Streamlit secrets — locally
in `.streamlit/secrets.toml`, or on Streamlit Cloud under your app's
Settings → Secrets:

```toml
[sheets]
dashboard = "PASTE_YOUR_GOOGLE_SHEET_ID_HERE"
```

Your Sheet ID is the long string in your sheet's URL:

```
https://docs.google.com/spreadsheets/d/  1AbCxyz123_THIS_IS_YOUR_ID  /edit
```

**Important:** the app expects these tabs to exist, named exactly:
- `Machines`
- `Warehouse_Products`
- `Txn_Daily`
- `Txn_Hourly`
- `Txn_Failures`
- `Txn_Product`
- `Metrics_Summary`
- `Rev_DoD`
- `Rev_MoM`
- `Refill_Hourly`
- `Refill_Product` (optional — a per-product refill breakdown shows up once this has rows)
- `SKU_Category_Map`
- `SKU_Mix`

Tabs are matched by name, not position, so you can reorder them freely in
the sheet.

### Optional: Accounts / HR tabs

The **Accounts** and **HR** tabs are unrelated to the vending-sales sheet
above — they read a separate bank/ledger sheet. If you use them, add:

```toml
[sheets]
dashboard = "..."
accounts = "PASTE_YOUR_ACCOUNTS_SHEET_ID_HERE"

[gids.accounts]
accounts = "PASTE_THE_ACCOUNTS_TAB_GID_HERE"
```

(Find the gid in that tab's URL, after `#gid=`.) Leave these out and the
Accounts/HR tabs will just show an info message instead of erroring.

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
- Is `dashboard` under `[sheets]` in your secrets actually set to your real
  sheet ID (not left as the placeholder)?
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

- **Pace-adjusted "Today":** if the latest date in the sheet is also today
  (by the server's clock), that day's row is a partial day, not a finished
  one. The app detects this from the clock and the fleet's own hour-of-day
  revenue pattern, shows a banner about it, and adjusts every Today
  comparison (Overview's snapshot, Needs Attention, the Today tab) to
  compare against the *same point in the day* rather than a full day —
  so a check at 11am isn't scored against yesterday's full 24 hours.
- **Sidebar:** date range picker, city filter, machine filter, manual
  refresh button
- **KPI row:** total revenue, units sold, average daily revenue, machines
  in view, failure rate — all respect the filters above
- **Overview tab:** D/D-1/D-2/average daily-revenue snapshot, daily revenue
  trend, lifetime top-performer leaderboard (by machine/location/warehouse)
- **Needs Attention tab:** pick a 1-5 day lookback window and see which
  machines stopped selling, dropped in revenue, or had elevated failures
  vs. their own trailing 30-day baseline — always anchored to the latest
  data, independent of the sidebar's date range
- **Today tab:** Today vs. Yesterday, Last 3 Days, Last Week, This Month
  and Last Month (shown as avg/day so every period is directly
  comparable), at machine or location level, for revenue, units,
  amount lost, or failure rate — plus This Month/Last Month revenue
  totals
- **Revenue & Sales tab:** daily revenue & units, revenue by hour of day,
  month-over-month trend (fleet-wide or drilled into one machine/
  location/warehouse), top products by revenue
- **Refilling tab:** refill quantity by hour of day, refill totals by
  machine
- **Failures tab:** dispense-timeout/paid-not-dispensed/payment-failed
  KPIs, amount lost over time and by machine, detailed monthly breakdown
  by error code
- **SKU Mix tab:** fleet-wide revenue by category, top products, and a
  category revenue-share breakdown per machine/location/warehouse (all
  time or last full month)
- **Machines tab:** machine directory with status/city/location/
  warehouse, machine counts by city, lifetime performance leaderboard
- **Outliers tab:** machines flagged by the IQR rule on a chosen metric
  (revenue, failure rate, amount lost, recent revenue momentum), plus
  the most volatile machines by day-to-day revenue and machines with an
  unusually high/low share of a product category
- **Accounts tab:** bank ledger KPIs, P&L snapshot and waterfall, cash
  flow analytics, full transaction log — reads the separate accounts
  sheet (see "Optional: Accounts / HR tabs" above)
- **HR tab:** payroll detected from the Accounts ledger — per-employee
  totals, monthly payroll trend, full payment history

---

## If something breaks on Streamlit Cloud

Click **Manage app** (bottom right of the deployed app) → it opens a log
panel. The error message there will usually point to a missing package
(add it to `requirements.txt`) or a data issue (check sheet tab names and
sharing settings, per Step 1).
