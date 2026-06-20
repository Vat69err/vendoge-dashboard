import requests

# Paste your real Sheet ID below (same one you put in app.py)
SHEET_ID = "1US77O6RV0ue_OdAAvF8u3H4YdR5MzmbIIaq6z7JzQHU"

# Paste each tab's gid below. Click the tab in your browser and copy the
# number after "#gid=" in the URL.
GIDS = {
    "Machine Wise Sales": "0",
    "Consolidated Refilling": "2119871943",
    "Out of Stock Log": "1944086957",
}

for name, gid in GIDS.items():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    r = requests.get(url)
    print("=" * 60)
    print("TAB:", name, "| GID:", gid)
    print("STATUS:", r.status_code)
    print("FIRST 200 CHARS:", r.text[:200])
    print()