import requests

# Paste your real Sheet ID below (same as in .streamlit/secrets.toml)
SHEET_ID = "YOUR_SHEET_ID_HERE"

# Paste each tab's gid below. Click the tab in your browser and copy the
# number after "#gid=" in the URL.
GIDS = {
    "Machine Wise Sales": "YOUR_SALES_GID_HERE",
    "Consolidated Refilling": "YOUR_REFILL_GID_HERE",
    "Out of Stock Log": "YOUR_STOCKOUT_GID_HERE",
}

for name, gid in GIDS.items():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    r = requests.get(url)
    print("=" * 60)
    print("TAB:", name, "| GID:", gid)
    print("STATUS:", r.status_code)
    print("FIRST 200 CHARS:", r.text[:200])
    print()
