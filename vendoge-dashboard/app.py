"""
Vendoge Operations Dashboard
-----------------------------
Reads live data from a public Google Sheet (3 tabs: Machine Wise Sales,
Consolidated Refilling, Out of Stock Log) and renders an interactive
Streamlit dashboard.

EDIT THIS ONE LINE before running -> put your Google Sheet ID below.
Find it in your sheet's URL:
https://docs.google.com/spreadsheets/d/  <-- THIS PART -->  /edit
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

PRIMARY = "#0E6E55"      # deep teal — vending green
ACCENT = "#F2A93B"       # warm amber — restock/alert accent
BG_CARD = "#F6F4EF"

st.set_page_config(
    page_title="Vendoge Dashboard",
    page_icon="🥤",
    layout="wide",
)

# ============================================================
# 1. CONFIG — loaded from Streamlit secrets
# ============================================================
try:
    SHEET_ID = st.secrets["sheet_id"]
    GIDS = {
        "sales": str(st.secrets["gids"]["sales"]),
        "refill": str(st.secrets["gids"]["refill"]),
        "stockout": str(st.secrets["gids"]["stockout"]),
        "stock_in": str(st.secrets["gids"].get("stock_in", "")),
        "inventory": str(st.secrets["gids"].get("inventory", "")),
    }
except (KeyError, FileNotFoundError):
    st.error(
        "Missing secrets! This app needs `sheet_id` and `gids` set up in "
        "Streamlit secrets — locally in `.streamlit/secrets.toml`, or on "
        "Streamlit Cloud under your app's Settings > Secrets."
    )
    st.stop()

# ============================================================
# 2. DATA LOADING — pulls live CSV export of each tab
# ============================================================


def _sheet_url(gid: str) -> str:
    """Build the raw CSV export URL for one tab of a PUBLIC google sheet, by gid."""
    return (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export"
        f"?format=csv&gid={gid}"
    )


@st.cache_data(ttl=300, show_spinner="Pulling latest data from Google Sheets...")
def load_data():
    sales = pd.read_csv(_sheet_url(GIDS["sales"]))
    refill = pd.read_csv(_sheet_url(GIDS["refill"]))
    stockout = pd.read_csv(_sheet_url(GIDS["stockout"]))

    sales["date"] = pd.to_datetime(sales["date"], errors="coerce")
    refill["date"] = pd.to_datetime(refill["date"], errors="coerce")
    stockout["date"] = pd.to_datetime(stockout["date"], errors="coerce")

    for col in ("machine",):
        if col in sales.columns:
            sales[col] = sales[col].astype(str)
    if "machine" in stockout.columns:
        stockout["machine"] = stockout["machine"].astype(str)

    stock_in = pd.DataFrame()
    if GIDS.get("stock_in"):
        stock_in = pd.read_csv(_sheet_url(GIDS["stock_in"]))
        stock_in["date"] = pd.to_datetime(stock_in["date"], errors="coerce")
        if "packets_added" in stock_in.columns:
            stock_in["packets_added"] = pd.to_numeric(stock_in["packets_added"], errors="coerce").fillna(0)

    inventory = pd.DataFrame()
    if GIDS.get("inventory"):
        inventory = pd.read_csv(_sheet_url(GIDS["inventory"]))
        inventory["date"] = pd.to_datetime(inventory["date"], errors="coerce")
        for col in ("units", "physical_count_yesterday_evening", "refilling_quantity",
                    "new_stock_added", "final_in_warehouse"):
            if col in inventory.columns:
                inventory[col] = pd.to_numeric(inventory[col], errors="coerce").fillna(0)

    return sales, refill, stockout, stock_in, inventory


try:
    sales_df, refill_df, stockout_df, stock_in_df, inventory_df = load_data()
except Exception as e:
    st.error(
        "Couldn't load the Google Sheet. Most likely causes:\n\n"
        "1. SHEET_ID in app.py hasn't been set to your real sheet ID yet, or\n"
        "2. The sheet isn't shared as 'Anyone with the link can view', or\n"
        "3. One of the GIDS in app.py is still a placeholder or wrong — "
        "click each tab in your browser and copy the number after '#gid=' in the URL."
    )
    st.caption(f"Technical detail: {e}")
    st.stop()

# ============================================================
# 3. SIDEBAR FILTERS
# ============================================================
st.sidebar.title("🥤 Vendoge")
st.sidebar.caption("Filters")

min_date = min(sales_df["date"].min(), refill_df["date"].min(), stockout_df["date"].min())
max_date = max(sales_df["date"].max(), refill_df["date"].max(), stockout_df["date"].max())

date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date.date(), max_date.date()),
    min_value=min_date.date(),
    max_value=max_date.date(),
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date.date(), max_date.date()

all_machines = sorted(sales_df["machine"].dropna().unique().tolist()) if "machine" in sales_df.columns else []
machine_sel = st.sidebar.multiselect("Machines", all_machines, default=all_machines, key="sidebar_machines")

if st.sidebar.button("🔄 Refresh data now"):
    st.cache_data.clear()
    # Drop the machine multiselect state so it resets to the freshly-loaded machine names
    st.session_state.pop("sidebar_machines", None)
    st.rerun()

st.sidebar.caption(f"Last pulled: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
st.sidebar.caption("Data auto-refreshes every 5 minutes.")


def in_range(df, col="date"):
    mask = (df[col].dt.date >= start_date) & (df[col].dt.date <= end_date)
    return df.loc[mask].copy()


sales_f = in_range(sales_df)
if machine_sel and "machine" in sales_f.columns:
    sales_f = sales_f[sales_f["machine"].isin(machine_sel)]
refill_f = in_range(refill_df)
stockout_f = in_range(stockout_df)
if machine_sel and "machine" in stockout_f.columns:
    stockout_f = stockout_f[stockout_f["machine"].isin(machine_sel)]

# ============================================================
# 4. HEADER + KPI ROW
# ============================================================
st.title("Vendoge Operations Dashboard")
st.caption("Live view of machine sales, refilling, and stock-outs.")

total_sales = sales_f["total_sales"].sum() if "total_sales" in sales_f else 0
total_qty = sales_f["total_qty"].sum() if "total_qty" in sales_f else 0
cash_share = (
    sales_f["cash_sales"].sum() / total_sales * 100 if total_sales and "cash_sales" in sales_f else 0
)
stockout_count = len(stockout_f)
active_days = sales_f["date"].dt.date.nunique() or 1
avg_daily_sales = total_sales / active_days

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Sales", f"₹{total_sales:,.0f}")
k2.metric("Units Sold", f"{total_qty:,.0f}")
k3.metric("Avg Daily Sales", f"₹{avg_daily_sales:,.0f}")
k4.metric("Cash Share", f"{cash_share:.1f}%")
k5.metric("Stock-out Events", f"{stockout_count:,}")

st.divider()

# ============================================================
# 5. PERIOD-AVERAGE HELPERS
# ============================================================

def period_avgs(daily_series: pd.Series) -> dict:
    """
    Given a date-indexed daily Series, return the latest day value, the two
    preceding days, and per-day averages for 3-day, 7-day, 15-day windows
    and the full history.  Windows are inclusive of the latest date.
    Also returns the actual calendar dates for latest/day_m1/day_m2 so labels
    can show the real date instead of a relative offset.
    """
    if daily_series.empty:
        return {
            "latest": 0.0, "day_m1": 0.0, "day_m2": 0.0,
            "avg_3d": 0.0, "avg_7d": 0.0, "avg_15d": 0.0, "avg_all": 0.0,
            "date_latest": None, "date_m1": None, "date_m2": None,
        }
    s = daily_series.sort_index()
    latest_date = s.index.max()
    dates = s.index.tolist()

    def _avg(n):
        cutoff = latest_date - timedelta(days=n - 1)
        w = s[s.index >= cutoff]
        return float(w.mean()) if len(w) else 0.0

    return {
        "latest": float(s.iloc[-1]),
        "day_m1": float(s.iloc[-2]) if len(s) >= 2 else 0.0,
        "day_m2": float(s.iloc[-3]) if len(s) >= 3 else 0.0,
        "avg_3d": _avg(3),
        "avg_7d": _avg(7),
        "avg_15d": _avg(15),
        "avg_all": float(s.mean()),
        "date_latest": dates[-1],
        "date_m1": dates[-2] if len(dates) >= 2 else None,
        "date_m2": dates[-3] if len(dates) >= 3 else None,
    }


def snapshot_row(label: str, avgs: dict, fmt: str = "₹{:,.0f}", inverse: bool = False):
    """
    Render a labelled 7-column snapshot strip with delta arrows.
    Latest shows Δ vs Day-1; Day-1 shows Δ vs Day-2; averages show trend vs next wider window.
    Set inverse=True for metrics where a higher value is bad (e.g. stock-outs).
    """
    def _delta(a, b):
        """Return (formatted_delta, delta_color) for a vs b."""
        diff = a - b
        if b == 0:
            return None, "off"
        pct = diff / abs(b) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%", "inverse" if inverse else "normal"

    def _lbl(key):
        d = avgs.get(key)
        return d.strftime("%-d %b") if d else "—"

    dc = "inverse" if inverse else "normal"
    d_lat, col_lat = _delta(avgs["latest"], avgs["day_m1"])
    d_m1, col_m1 = _delta(avgs["day_m1"], avgs["day_m2"])
    d_3v7, col_3v7 = _delta(avgs["avg_3d"], avgs["avg_7d"])
    d_7v15, col_7v15 = _delta(avgs["avg_7d"], avgs["avg_15d"])
    d_15va, col_15va = _delta(avgs["avg_15d"], avgs["avg_all"])

    st.caption(f"**{label}**")
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric(_lbl("date_latest"), fmt.format(avgs["latest"]), delta=d_lat, delta_color=col_lat)
    c2.metric(_lbl("date_m1") + " (D−1)", fmt.format(avgs["day_m1"]), delta=d_m1, delta_color=col_m1)
    c3.metric(_lbl("date_m2") + " (D−2)", fmt.format(avgs["day_m2"]))
    c4.metric("Avg 3d", fmt.format(avgs["avg_3d"]), delta=d_3v7, delta_color=col_3v7)
    c5.metric("Avg 7d", fmt.format(avgs["avg_7d"]), delta=d_7v15, delta_color=col_7v15)
    c6.metric("Avg 15d", fmt.format(avgs["avg_15d"]), delta=d_15va, delta_color=col_15va)
    c7.metric("Overall Avg/Day", fmt.format(avgs["avg_all"]))


# ============================================================
# 6. SHARED PREDICTION HELPERS (used by Predictions + Inventory tabs)
# ============================================================
_pred_today = sales_df["date"].max()

_pred_cols = {"product_id", "product_name", "total_qty"}
if _pred_cols.issubset(sales_df.columns):
    sales_by_product_day = (
        sales_df.groupby(["product_id", "product_name", sales_df["date"]])["total_qty"]
        .sum().reset_index()
    )
else:
    sales_by_product_day = pd.DataFrame(columns=["product_id", "product_name", "date", "total_qty"])

_refill_pred_cols = {"product_id", "product_name", "brand_name", "qty_after_refill"}
if _refill_pred_cols.issubset(refill_df.columns) and not refill_df.empty:
    latest_refill = (
        refill_df.sort_values("date")
        .groupby("product_id")
        .tail(1)[["product_id", "product_name", "brand_name", "date", "qty_after_refill"]]
        .rename(columns={"date": "last_refill_date"})
    )
else:
    latest_refill = pd.DataFrame(columns=["product_id", "product_name", "brand_name", "last_refill_date", "qty_after_refill"])


def build_stock_table(rate_window_days: int = 14) -> pd.DataFrame:
    rows = []
    for _, r in latest_refill.iterrows():
        pid = r["product_id"]
        prod_sales = sales_by_product_day[sales_by_product_day["product_id"] == pid]
        sold_since_refill = prod_sales.loc[
            prod_sales["date"] > r["last_refill_date"], "total_qty"
        ].sum()
        current_stock = max(r["qty_after_refill"] - sold_since_refill, 0)
        recent = prod_sales.loc[
            prod_sales["date"] > _pred_today - pd.Timedelta(days=rate_window_days)
        ]
        daily_rate = recent["total_qty"].sum() / rate_window_days
        days_remaining = current_stock / daily_rate if daily_rate > 0 else np.inf
        rows.append({
            "product_id": pid,
            "product_name": r["product_name"],
            "brand_name": r["brand_name"],
            "last_refill_date": r["last_refill_date"].date(),
            "current_stock_est": int(current_stock),
            "daily_sales_rate": round(daily_rate, 2),
            "days_remaining": days_remaining,
        })
    return pd.DataFrame(rows)


def urgency_label(days):
    if not np.isfinite(days):
        return "⚪ No recent sales"
    if days <= 2:
        return "🔴 Urgent"
    if days <= 5:
        return "🟠 Soon"
    return "🟢 OK"


# Pre-compute stock table at default 14-day window for cross-tab use
_default_stock_table = build_stock_table(rate_window_days=14)
if not _default_stock_table.empty:
    _default_stock_table["urgency"] = _default_stock_table["days_remaining"].apply(urgency_label)

# ============================================================
# 7. TABS
# ============================================================
tab_overview, tab_sales, tab_refill, tab_stockout, tab_predict, tab_ops, tab_inv, tab_verka = st.tabs(
    ["📊 Overview", "🛒 Machine Sales", "🔁 Refilling", "🚫 Stock-Outs", "🔮 Predictions", "⚙️ Operations", "📦 Inventory & Stock", "🥛 Verka"]
)

# ---------- OVERVIEW ----------
with tab_overview:
    st.subheader("Daily Performance Snapshot")
    st.caption("How today compares to recent averages — all figures are per-day totals.")

    # Derive column labels from actual dates in the sales series
    _date_series = sales_f.groupby(sales_f["date"].dt.date)["total_sales"].sum() if "total_sales" in sales_f.columns and not sales_f.empty else pd.Series(dtype=float)
    _ref = period_avgs(_date_series)
    _col_latest = _ref["date_latest"].strftime("%-d %b") if _ref["date_latest"] else "Latest"
    _col_m1 = (_ref["date_m1"].strftime("%-d %b") + " (D−1)") if _ref["date_m1"] else "D−1"
    _col_m2 = (_ref["date_m2"].strftime("%-d %b") + " (D−2)") if _ref["date_m2"] else "D−2"

    def _pct_delta(a, b):
        if b == 0:
            return "—"
        pct = (a - b) / abs(b) * 100
        sign = "▲" if pct >= 0 else "▼"
        return f"{sign} {abs(pct):.1f}%"

    _snap_rows = []
    if "total_sales" in sales_f.columns and not sales_f.empty:
        _a = period_avgs(sales_f.groupby(sales_f["date"].dt.date)["total_sales"].sum())
        _snap_rows.append({
            "Metric": "Sales (₹)",
            _col_latest: f"₹{_a['latest']:,.0f}",
            _col_m1: f"₹{_a['day_m1']:,.0f}",
            _col_m2: f"₹{_a['day_m2']:,.0f}",
            "Δ vs D−1": _pct_delta(_a["latest"], _a["day_m1"]),
            "Avg 3d": f"₹{_a['avg_3d']:,.0f}",
            "Avg 7d": f"₹{_a['avg_7d']:,.0f}",
            "Avg 15d": f"₹{_a['avg_15d']:,.0f}",
            "Overall Avg/Day": f"₹{_a['avg_all']:,.0f}",
        })
    if "total_qty" in sales_f.columns and not sales_f.empty:
        _a = period_avgs(sales_f.groupby(sales_f["date"].dt.date)["total_qty"].sum())
        _snap_rows.append({
            "Metric": "Units Sold",
            _col_latest: f"{_a['latest']:,.0f}",
            _col_m1: f"{_a['day_m1']:,.0f}",
            _col_m2: f"{_a['day_m2']:,.0f}",
            "Δ vs D−1": _pct_delta(_a["latest"], _a["day_m1"]),
            "Avg 3d": f"{_a['avg_3d']:,.1f}",
            "Avg 7d": f"{_a['avg_7d']:,.1f}",
            "Avg 15d": f"{_a['avg_15d']:,.1f}",
            "Overall Avg/Day": f"{_a['avg_all']:,.1f}",
        })
    if not stockout_f.empty:
        _a = period_avgs(stockout_f.groupby(stockout_f["date"].dt.date).size())
        _snap_rows.append({
            "Metric": "Stock-out Events",
            _col_latest: f"{_a['latest']:,.0f}",
            _col_m1: f"{_a['day_m1']:,.0f}",
            _col_m2: f"{_a['day_m2']:,.0f}",
            "Δ vs D−1": _pct_delta(_a["latest"], _a["day_m1"]),
            "Avg 3d": f"{_a['avg_3d']:,.1f}",
            "Avg 7d": f"{_a['avg_7d']:,.1f}",
            "Avg 15d": f"{_a['avg_15d']:,.1f}",
            "Overall Avg/Day": f"{_a['avg_all']:,.1f}",
        })

    if _snap_rows:
        st.dataframe(
            pd.DataFrame(_snap_rows).set_index("Metric"),
            use_container_width=True,
        )

    st.divider()
    st.subheader("Trends & Breakdown")

    col1, col2 = st.columns((2, 1))

    with col1:
        daily = sales_f.groupby(sales_f["date"].dt.date)["total_sales"].sum().reset_index()
        daily.columns = ["date", "total_sales"]
        fig = px.area(
            daily, x="date", y="total_sales",
            title="Daily Sales Trend",
            color_discrete_sequence=[PRIMARY],
        )
        fig.update_layout(yaxis_title="Sales (₹)", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        by_machine = sales_f.groupby("machine")["total_sales"].sum().reset_index()
        fig2 = px.pie(
            by_machine, names="machine", values="total_sales",
            title="Sales Split by Machine", hole=0.5,
            color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C"],
        )
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        top_products = (
            sales_f.groupby("product_name")["total_sales"]
            .sum().sort_values(ascending=False).head(10).reset_index()
        )
        fig3 = px.bar(
            top_products, x="total_sales", y="product_name", orientation="h",
            title="Top 10 Products by Sales",
            color_discrete_sequence=[PRIMARY],
        )
        fig3.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Sales (₹)", yaxis_title="")
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        cat = sales_f.groupby("category")["total_sales"].sum().sort_values(ascending=False).reset_index()
        fig4 = px.bar(
            cat, x="category", y="total_sales",
            title="Sales by Category",
            color_discrete_sequence=[ACCENT],
        )
        fig4.update_layout(xaxis_title="", yaxis_title="Sales (₹)")
        st.plotly_chart(fig4, use_container_width=True)

    # Brand breakdown
    if "brand_name" in sales_f.columns:
        st.subheader("Sales by Brand")
        br_c1, br_c2 = st.columns(2)
        with br_c1:
            brand_sales = (
                sales_f.groupby("brand_name")["total_sales"]
                .sum().sort_values(ascending=False).reset_index()
            )
            fig_br = px.bar(
                brand_sales.sort_values("total_sales"),
                x="total_sales", y="brand_name", orientation="h",
                title="Total Sales by Brand",
                color_discrete_sequence=[PRIMARY],
            )
            fig_br.update_layout(xaxis_title="Sales (₹)", yaxis_title="")
            st.plotly_chart(fig_br, use_container_width=True)

        with br_c2:
            if "machine" in sales_f.columns:
                brand_machine = (
                    sales_f.groupby(["brand_name", "machine"])["total_sales"]
                    .sum().reset_index()
                )
                fig_bm = px.bar(
                    brand_machine, x="brand_name", y="total_sales", color="machine",
                    barmode="stack",
                    title="Brand Sales Split by Machine",
                    color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C"],
                )
                fig_bm.update_layout(xaxis_title="", yaxis_title="Sales (₹)", legend_title="Machine")
                st.plotly_chart(fig_bm, use_container_width=True)

# ---------- MACHINE SALES ----------
with tab_sales:
    if "total_sales" in sales_f.columns and "machine" in sales_f.columns and not sales_f.empty:
        _ms_daily = sales_f.groupby(sales_f["date"].dt.date)["total_sales"].sum()
        snapshot_row("Daily Sales — all selected machines (₹)", period_avgs(_ms_daily))

        # Per-machine breakdown table with real date labels
        _machines_snap = sorted(sales_f["machine"].dropna().unique())
        if len(_machines_snap) > 1:
            # Derive date labels from the combined series
            _all_daily = sales_f.groupby(sales_f["date"].dt.date)["total_sales"].sum()
            _ref_a = period_avgs(_all_daily)
            _mc_latest = _ref_a["date_latest"].strftime("%-d %b") if _ref_a["date_latest"] else "Latest"
            _mc_m1 = (_ref_a["date_m1"].strftime("%-d %b") + " (D−1)") if _ref_a["date_m1"] else "D−1"
            _mc_m2 = (_ref_a["date_m2"].strftime("%-d %b") + " (D−2)") if _ref_a["date_m2"] else "D−2"

            _snap_rows = []
            for _m in _machines_snap:
                _s = sales_f[sales_f["machine"] == _m].groupby(sales_f["date"].dt.date)["total_sales"].sum()
                _a = period_avgs(_s)
                _d = _a["latest"] - _a["day_m1"]
                _dpct = f"{'▲' if _d >= 0 else '▼'} {abs(_d / _a['day_m1'] * 100):.1f}%" if _a["day_m1"] else "—"
                _snap_rows.append({
                    "Machine": _m,
                    _mc_latest: f"₹{_a['latest']:,.0f}",
                    _mc_m1: f"₹{_a['day_m1']:,.0f}",
                    _mc_m2: f"₹{_a['day_m2']:,.0f}",
                    "Δ vs D−1": _dpct,
                    "Avg 3d": f"₹{_a['avg_3d']:,.0f}",
                    "Avg 7d": f"₹{_a['avg_7d']:,.0f}",
                    "Avg 15d": f"₹{_a['avg_15d']:,.0f}",
                    "Overall Avg/Day": f"₹{_a['avg_all']:,.0f}",
                })
            st.dataframe(pd.DataFrame(_snap_rows), use_container_width=True, hide_index=True)
        st.divider()

    # ---- Top products per machine with D-1/D-2/avg breakdown ----
    if "machine" in sales_f.columns and "product_name" in sales_f.columns and not sales_f.empty:
        st.subheader("🏆 Top-Selling Products per Machine")
        _tp_n = st.slider("Show top N products per machine", 3, 15, 5, key="ms_topn")

        # Derive shared date labels from overall daily series
        _tp_daily = sales_f.groupby(sales_f["date"].dt.date)["total_sales"].sum()
        _tp_ref = period_avgs(_tp_daily)
        _tp_lat = _tp_ref["date_latest"].strftime("%-d %b") if _tp_ref["date_latest"] else "Latest"
        _tp_m1 = (_tp_ref["date_m1"].strftime("%-d %b") + " (D−1)") if _tp_ref["date_m1"] else "D−1"
        _tp_m2 = (_tp_ref["date_m2"].strftime("%-d %b") + " (D−2)") if _tp_ref["date_m2"] else "D−2"

        _tp_machines = sorted(sales_f["machine"].dropna().unique())
        _tp_cols = st.columns(min(len(_tp_machines), 3))

        for _ti, _machine in enumerate(_tp_machines):
            _mdf = sales_f[sales_f["machine"] == _machine]

            # Top N products by total sales in the selected period
            _top_prods = (
                _mdf.groupby("product_name")["total_sales"]
                .sum().sort_values(ascending=False).head(_tp_n).index.tolist()
            )

            with _tp_cols[_ti % len(_tp_cols)]:
                # Bar chart: total sales over selected period
                _bar_data = (
                    _mdf[_mdf["product_name"].isin(_top_prods)]
                    .groupby("product_name")["total_sales"].sum()
                    .reset_index().sort_values("total_sales")
                )
                _fig_tp = px.bar(
                    _bar_data, x="total_sales", y="product_name", orientation="h",
                    title=f"{_machine}",
                    color_discrete_sequence=[PRIMARY],
                )
                _fig_tp.update_layout(
                    xaxis_title="Sales (₹)", yaxis_title="",
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=max(220, len(_top_prods) * 38),
                )
                st.plotly_chart(_fig_tp, use_container_width=True)

                # D-1 / D-2 / avg table
                _tp_rows = []
                for _prod in _top_prods:
                    _ps = _mdf[_mdf["product_name"] == _prod].groupby(_mdf["date"].dt.date)["total_sales"].sum()
                    _pa = period_avgs(_ps)
                    _d = _pa["latest"] - _pa["day_m1"]
                    _dpct = (
                        f"{'▲' if _d >= 0 else '▼'} {abs(_d / _pa['day_m1'] * 100):.0f}%"
                        if _pa["day_m1"] else "—"
                    )
                    _tp_rows.append({
                        "Product": _prod,
                        _tp_lat: f"₹{_pa['latest']:,.0f}",
                        _tp_m1: f"₹{_pa['day_m1']:,.0f}",
                        _tp_m2: f"₹{_pa['day_m2']:,.0f}",
                        "Δ": _dpct,
                        "Avg 3d": f"₹{_pa['avg_3d']:,.0f}",
                        "Avg 7d": f"₹{_pa['avg_7d']:,.0f}",
                        "Avg 15d": f"₹{_pa['avg_15d']:,.0f}",
                        "Overall": f"₹{_pa['avg_all']:,.0f}",
                    })
                st.dataframe(
                    pd.DataFrame(_tp_rows),
                    use_container_width=True, hide_index=True,
                )

        st.divider()

    c1, c2 = st.columns(2)
    with c1:
        brand_sel = st.multiselect(
            "Brand", sorted(sales_f["brand_name"].dropna().unique().tolist()) if "brand_name" in sales_f.columns else []
        )
    with c2:
        cat_sel = st.multiselect(
            "Category", sorted(sales_f["category"].dropna().unique().tolist()) if "category" in sales_f.columns else []
        )

    detail = sales_f.copy()
    if brand_sel:
        detail = detail[detail["brand_name"].isin(brand_sel)]
    if cat_sel:
        detail = detail[detail["category"].isin(cat_sel)]

    trend = detail.groupby([detail["date"].dt.date, "machine"])["total_sales"].sum().reset_index()
    trend.columns = ["date", "machine", "total_sales"]
    fig5 = px.line(
        trend, x="date", y="total_sales", color="machine", markers=True,
        title="Sales Trend by Machine",
        color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C"],
    )
    st.plotly_chart(fig5, use_container_width=True)

    payment = detail.groupby("machine")[["cash_sales", "cashless_sales"]].sum().reset_index()
    payment_m = payment.melt(id_vars="machine", var_name="type", value_name="amount")
    fig6 = px.bar(
        payment_m, x="machine", y="amount", color="type", barmode="group",
        title="Cash vs Cashless by Machine",
        color_discrete_sequence=[PRIMARY, ACCENT],
    )
    st.plotly_chart(fig6, use_container_width=True)

    if "brand_name" in detail.columns:
        st.subheader("Brand Performance")
        bd_c1, bd_c2 = st.columns(2)
        with bd_c1:
            brand_rev = (
                detail.groupby("brand_name")["total_sales"]
                .sum().sort_values(ascending=False).reset_index()
            )
            fig_bd1 = px.bar(
                brand_rev.sort_values("total_sales"),
                x="total_sales", y="brand_name", orientation="h",
                title="Revenue by Brand",
                color_discrete_sequence=[PRIMARY],
            )
            fig_bd1.update_layout(xaxis_title="Sales (₹)", yaxis_title="")
            st.plotly_chart(fig_bd1, use_container_width=True)

        with bd_c2:
            brand_qty = (
                detail.groupby("brand_name")["total_qty"]
                .sum().sort_values(ascending=False).reset_index()
            )
            fig_bd2 = px.bar(
                brand_qty.sort_values("total_qty"),
                x="total_qty", y="brand_name", orientation="h",
                title="Units Sold by Brand",
                color_discrete_sequence=[ACCENT],
            )
            fig_bd2.update_layout(xaxis_title="Units", yaxis_title="")
            st.plotly_chart(fig_bd2, use_container_width=True)

        if "machine" in detail.columns:
            brand_trend = (
                detail.groupby(["brand_name", detail["date"].dt.date])["total_sales"]
                .sum().reset_index()
            )
            brand_trend.columns = ["brand_name", "date", "total_sales"]
            fig_bt = px.line(
                brand_trend, x="date", y="total_sales", color="brand_name", markers=False,
                title="Brand Sales Trend Over Time",
            )
            fig_bt.update_layout(xaxis_title="", yaxis_title="Sales (₹)", legend_title="Brand")
            st.plotly_chart(fig_bt, use_container_width=True)

    st.subheader("Product-level detail")
    st.dataframe(
        detail.groupby(["product_name", "brand_name", "category"])[
            ["total_qty", "total_sales"]
        ].sum().sort_values("total_sales", ascending=False).reset_index(),
        use_container_width=True,
    )

# ---------- REFILLING ----------
with tab_refill:
    c1, c2 = st.columns(2)
    with c1:
        refillers = sorted(refill_f["refiller_name"].dropna().unique().tolist()) if "refiller_name" in refill_f.columns else []
        refiller_sel = st.multiselect("Refiller", refillers, default=refillers)
    with c2:
        st.metric("Total Refill Value", f"₹{refill_f['amount'].sum():,.0f}")

    rf = refill_f[refill_f["refiller_name"].isin(refiller_sel)] if refiller_sel else refill_f

    if not rf.empty:
        if "amount" in rf.columns:
            _rf_val = rf.groupby(rf["date"].dt.date)["amount"].sum()
            snapshot_row("Daily Refill Value (₹)", period_avgs(_rf_val))
        if "refill_qty" in rf.columns:
            _rf_qty = rf.groupby(rf["date"].dt.date)["refill_qty"].sum()
            snapshot_row("Daily Units Refilled", period_avgs(_rf_qty), fmt="{:,.0f}")
        st.divider()

    by_refiller = rf.groupby("refiller_name")["amount"].sum().reset_index()
    fig7 = px.bar(
        by_refiller, x="refiller_name", y="amount",
        title="Refill Value by Refiller",
        color_discrete_sequence=[PRIMARY],
    )
    fig7.update_layout(xaxis_title="", yaxis_title="Amount (₹)")
    st.plotly_chart(fig7, use_container_width=True)

    daily_refill = rf.groupby(rf["date"].dt.date)["refill_qty"].sum().reset_index()
    daily_refill.columns = ["date", "refill_qty"]
    fig8 = px.bar(
        daily_refill, x="date", y="refill_qty",
        title="Units Refilled per Day",
        color_discrete_sequence=[ACCENT],
    )
    st.plotly_chart(fig8, use_container_width=True)

    if "brand_name" in rf.columns:
        st.subheader("Refill by Brand")
        rb_c1, rb_c2 = st.columns(2)
        with rb_c1:
            brand_refill_val = (
                rf.groupby("brand_name")["amount"].sum().sort_values(ascending=False).reset_index()
            )
            fig_rb1 = px.bar(
                brand_refill_val.sort_values("amount"),
                x="amount", y="brand_name", orientation="h",
                title="Refill Value by Brand (₹)",
                color_discrete_sequence=[PRIMARY],
            )
            fig_rb1.update_layout(xaxis_title="Amount (₹)", yaxis_title="")
            st.plotly_chart(fig_rb1, use_container_width=True)

        with rb_c2:
            if "refill_qty" in rf.columns:
                brand_refill_qty = (
                    rf.groupby("brand_name")["refill_qty"].sum().sort_values(ascending=False).reset_index()
                )
                fig_rb2 = px.bar(
                    brand_refill_qty.sort_values("refill_qty"),
                    x="refill_qty", y="brand_name", orientation="h",
                    title="Units Refilled by Brand",
                    color_discrete_sequence=[ACCENT],
                )
                fig_rb2.update_layout(xaxis_title="Units", yaxis_title="")
                st.plotly_chart(fig_rb2, use_container_width=True)

    st.subheader("Refill log")
    st.dataframe(rf.sort_values("date", ascending=False), use_container_width=True)

# ---------- STOCK-OUTS ----------
with tab_stockout:
    if stockout_f.empty:
        st.info("No stock-out events in this date range. 🎉")
    else:
        _so_daily = stockout_f.groupby(stockout_f["date"].dt.date).size()
        snapshot_row("Daily Stock-out Events", period_avgs(_so_daily), fmt="{:,.1f}", inverse=True)
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            by_day_machine = (
                stockout_f.groupby([stockout_f["date"].dt.date, "machine"])
                .size().reset_index(name="events")
            )
            by_day_machine.columns = ["date", "machine", "events"]
            fig9 = px.bar(
                by_day_machine, x="date", y="events", color="machine",
                title="Stock-out Events per Day",
                color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C"],
            )
            st.plotly_chart(fig9, use_container_width=True)

        with c2:
            top_oos = (
                stockout_f["product_name"].value_counts().head(10).reset_index()
            )
            top_oos.columns = ["product_name", "events"]
            fig10 = px.bar(
                top_oos, x="events", y="product_name", orientation="h",
                title="Most Frequently Out-of-Stock Products",
                color_discrete_sequence=[ACCENT],
            )
            fig10.update_layout(yaxis={"categoryorder": "total ascending"}, yaxis_title="")
            st.plotly_chart(fig10, use_container_width=True)

        if "type" in stockout_f.columns:
            type_counts = stockout_f["type"].value_counts().reset_index()
            type_counts.columns = ["type", "events"]
            fig11 = px.pie(
                type_counts, names="type", values="events", hole=0.5,
                title="Stock-out Type (Cash vs Cashless)",
                color_discrete_sequence=[PRIMARY, ACCENT],
            )
            st.plotly_chart(fig11, use_container_width=True)

        st.subheader("Stock-out log")
        st.dataframe(stockout_f.sort_values("date", ascending=False), use_container_width=True)

# ---------- PREDICTIONS ----------
with tab_predict:
    st.info(
        "📌 Heads up: your Consolidated Refilling sheet doesn't record which "
        "machine each refill was for, only the product and date. So the stock "
        "and refill predictions below are calculated **per product across all "
        "your machines combined**, not per individual machine. Sales forecasts "
        "can still be split by machine."
    )

    st.subheader("📈 Sales Forecast")
    forecast_col1, forecast_col2 = st.columns(2)
    with forecast_col1:
        forecast_machine = st.selectbox(
            "Machine", ["All machines"] + (sorted(sales_df["machine"].dropna().unique().tolist()) if "machine" in sales_df.columns else [])
        )
    with forecast_col2:
        forecast_horizon = st.slider("Days to forecast ahead", 3, 21, 7)

    fc_base = sales_df if forecast_machine == "All machines" else sales_df[sales_df["machine"] == forecast_machine]
    fc_daily = fc_base.groupby(fc_base["date"].dt.date)["total_sales"].sum().reset_index()
    fc_daily.columns = ["date", "total_sales"]
    fc_daily = fc_daily.sort_values("date")

    if len(fc_daily) < 4:
        st.warning("Not enough daily history yet to build a reliable forecast (need at least 4 days).")
    else:
        # Use only the most recent 30 days of history so the trend reflects recent behavior
        fc_recent = fc_daily.tail(30).reset_index(drop=True)
        x = np.arange(len(fc_recent))
        y = fc_recent["total_sales"].values
        coeffs = np.polyfit(x, y, 1)
        trend = np.poly1d(coeffs)

        future_x = np.arange(len(fc_recent), len(fc_recent) + forecast_horizon)
        forecast_vals = np.clip(trend(future_x), 0, None)
        future_dates = pd.date_range(
            pd.Timestamp(fc_daily["date"].max()) + pd.Timedelta(days=1), periods=forecast_horizon
        ).date

        hist_plot = fc_daily.rename(columns={"total_sales": "value"})
        hist_plot["kind"] = "Actual"
        fcst_plot = pd.DataFrame({"date": future_dates, "value": forecast_vals, "kind": "Forecast"})
        combined = pd.concat([hist_plot, fcst_plot], ignore_index=True)

        fig_fc = px.line(
            combined, x="date", y="value", color="kind", markers=True,
            title=f"Sales Forecast — {forecast_machine}",
            color_discrete_map={"Actual": PRIMARY, "Forecast": ACCENT},
        )
        fig_fc.update_layout(yaxis_title="Sales (₹)", xaxis_title="")
        st.plotly_chart(fig_fc, use_container_width=True)

        total_forecast = forecast_vals.sum()
        st.caption(
            f"Projected total sales over the next {forecast_horizon} days: "
            f"**₹{total_forecast:,.0f}** (simple linear trend on the last 30 days of data — "
            "treat this as a rough directional estimate, not a guarantee)."
        )

    st.divider()

    st.subheader("📦 Suggested Purchase Orders")
    st.caption(
        "These suggestions are built entirely from assumptions you control below — "
        "adjust them to match how your supply chain actually works."
    )

    with st.expander("⚙️ Assumptions", expanded=True):
        a1, a2, a3 = st.columns(3)
        with a1:
            rate_window = st.slider(
                "Sales rate lookback window (days)", 7, 30, 14,
                help="How many recent days to average daily sales over, to estimate demand.",
            )
            coverage_days = st.slider(
                "Days of demand to cover with this order", 3, 30, 14,
                help="How many days forward this order should keep you stocked.",
            )
        with a2:
            lead_time_days = st.slider(
                "Supplier lead time (days)", 0, 14, 3,
                help="Days between placing an order and it arriving. Stock keeps depleting during this time, so it's added to the coverage window.",
            )
            safety_pct = st.slider(
                "Safety buffer (%)", 0, 50, 20,
                help="Extra cushion on top of forecast demand, for unexpected spikes.",
            )
        with a3:
            pack_size = st.number_input(
                "Round orders up to multiples of", min_value=1, value=1, step=1,
                help="Set this to your case/carton size if your supplier only sells in fixed pack quantities.",
            )
            min_rate_filter = st.slider(
                "Hide products selling below (units/day)", 0.0, 5.0, 0.0, step=0.1,
                help="Filter out very slow-moving products that don't need active ordering attention.",
            )

    stock_table = build_stock_table(rate_window_days=rate_window)
    stock_table["urgency"] = stock_table["days_remaining"].apply(urgency_label)

    # latest known unit price per product, for cost estimates
    latest_price = (
        sales_df.sort_values("date").groupby("product_id")["price"].last()
    )
    stock_table = stock_table.merge(
        latest_price.rename("unit_price"), on="product_id", how="left"
    )

    total_window = coverage_days + lead_time_days
    po_table = stock_table.copy()
    po_table["forecast_demand"] = po_table["daily_sales_rate"] * total_window
    raw_order = (
        po_table["forecast_demand"] * (1 + safety_pct / 100) - po_table["current_stock_est"]
    ).clip(lower=0)
    if pack_size > 1:
        po_table["suggested_order"] = (np.ceil(raw_order / pack_size) * pack_size).astype(int)
    else:
        po_table["suggested_order"] = raw_order.round().astype(int)
    po_table["estimated_cost"] = po_table["suggested_order"] * po_table["unit_price"].fillna(0)

    po_table = po_table[po_table["daily_sales_rate"] >= min_rate_filter]
    po_table = po_table[po_table["suggested_order"] > 0].sort_values(
        "suggested_order", ascending=False
    )

    if po_table.empty:
        st.info("No restocking needed at current demand levels and assumptions.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Products to Reorder", len(po_table))
        m2.metric("Total Units Suggested", f"{po_table['suggested_order'].sum():,.0f}")
        m3.metric("Estimated Order Cost", f"₹{po_table['estimated_cost'].sum():,.0f}")
        m4.metric(
            "🔴 Urgent Among These",
            int((po_table["urgency"] == "🔴 Urgent").sum()),
        )

        demand_col = f"Forecast Demand ({total_window}d)"
        po_display = po_table[[
            "product_name", "brand_name", "urgency", "current_stock_est",
            "daily_sales_rate", "forecast_demand", "suggested_order",
            "unit_price", "estimated_cost",
        ]].rename(columns={
            "product_name": "Product", "brand_name": "Brand", "urgency": "Urgency",
            "current_stock_est": "Current Stock", "daily_sales_rate": "Avg Daily Sales",
            "forecast_demand": demand_col,
            "suggested_order": "Suggested Order Qty", "unit_price": "Unit Price (₹)",
            "estimated_cost": "Est. Cost (₹)",
        })
        po_display[demand_col] = po_display[demand_col].round(1)
        po_display["Unit Price (₹)"] = po_display["Unit Price (₹)"].round(2)
        po_display["Est. Cost (₹)"] = po_display["Est. Cost (₹)"].round(0)

        st.dataframe(po_display, use_container_width=True, hide_index=True)

        top_n = po_table.head(15).sort_values("suggested_order")
        fig_po = px.bar(
            top_n, x="suggested_order", y="product_name", orientation="h",
            title="Top Priority Orders by Quantity",
            color_discrete_sequence=[ACCENT],
            hover_data={"estimated_cost": ":.0f"},
        )
        fig_po.update_layout(xaxis_title="Suggested Order Qty", yaxis_title="")
        st.plotly_chart(fig_po, use_container_width=True)

        st.caption(
            "Suggested Order Qty = (forecast demand over coverage + lead time, plus safety buffer) "
            "− current estimated stock, rounded up to your pack size. "
            "Cross-check against your actual warehouse counts before placing real orders — "
            "the 'current stock' figure is an estimate based on the last recorded refill."
        )

# ============================================================
# 7. OPERATIONS TAB
# ============================================================
with tab_ops:

    # ---- 7a. Suggested refill times ----
    st.subheader("🕐 Suggested Refill Times")
    st.caption(
        "Your sales data doesn't include time-of-day, so these windows are derived from "
        "daily depletion rate, stockout patterns by day-of-week, and standard vending "
        "operating hours (8 am – 8 pm). Adjust the assumptions below to match your routes."
    )

    dow_labels = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

    rt_c1, rt_c2, rt_c3 = st.columns(3)
    with rt_c1:
        ops_start = st.number_input("Machine operating hours: start", min_value=0, max_value=23, value=8, step=1, key="ops_start")
    with rt_c2:
        ops_end = st.number_input("End", min_value=1, max_value=24, value=20, step=1, key="ops_end")
    with rt_c3:
        default_refills = st.selectbox("Default refills per day (applied to all machines unless overridden)", [1, 2, 3], index=1, key="ops_refills")

    machines_all = sorted(sales_df["machine"].dropna().unique()) if "machine" in sales_df.columns else []
    machine_refills = {}
    if machines_all:
        st.markdown("**Override refills per day per machine (optional):**")
        override_cols = st.columns(min(len(machines_all), 4))
        for i, m in enumerate(machines_all):
            with override_cols[i % len(override_cols)]:
                machine_refills[m] = st.selectbox(m, [1, 2, 3], index=default_refills - 1, key=f"refills_{m}")

    # Day-of-week demand index per machine (normalised avg qty)
    if not sales_df.empty and "machine" in sales_df.columns:
        sales_df["_dow"] = sales_df["date"].dt.dayofweek
        dow_demand = (
            sales_df.groupby(["machine", "_dow"])["total_qty"]
            .mean().reset_index()
        )
        # Stockout days by dow
        if not stockout_df.empty and "machine" in stockout_df.columns:
            stockout_df["_dow"] = stockout_df["date"].dt.dayofweek
            so_dow_machine = (
                stockout_df.groupby(["machine", "_dow"]).size().reset_index(name="so_count")
            )
        else:
            so_dow_machine = pd.DataFrame(columns=["machine", "_dow", "so_count"])

        st.markdown("---")
        st.markdown("**Recommended refill schedule:**")

        for machine in machines_all:
            n = machine_refills.get(machine, default_refills)
            span = ops_end - ops_start
            interval = span / n

            # Which day of week has most stockouts or highest sales for this machine?
            m_demand = dow_demand[dow_demand["machine"] == machine].sort_values("_dow")
            m_so = so_dow_machine[so_dow_machine["machine"] == machine] if not so_dow_machine.empty else pd.DataFrame()

            # Score each day: normalised sales + normalised stockouts
            if not m_demand.empty:
                max_qty = m_demand["total_qty"].max() or 1
                m_demand = m_demand.copy()
                m_demand["score"] = m_demand["total_qty"] / max_qty
                if not m_so.empty:
                    m_demand = m_demand.merge(m_so[["_dow", "so_count"]], on="_dow", how="left")
                    m_demand["so_count"] = m_demand["so_count"].fillna(0)
                    max_so = m_demand["so_count"].max() or 1
                    m_demand["score"] += m_demand["so_count"] / max_so
                peak_dow_row = m_demand.sort_values("score", ascending=False).iloc[0]
                peak_dow_name = dow_labels[int(peak_dow_row["_dow"])]
                prev_dow_name = dow_labels[(int(peak_dow_row["_dow"]) - 1) % 7]
            else:
                peak_dow_name = "—"
                prev_dow_name = "—"

            times = [f"{int(ops_start + i * interval):02d}:00" for i in range(n)]
            time_str = " → ".join(times)

            st.markdown(
                f"**{machine}** ({n}×/day) &nbsp;|&nbsp; "
                f"Refill at: **{time_str}** &nbsp;|&nbsp; "
                f"Peak demand day: **{peak_dow_name}** → prioritise full load on **{prev_dow_name}** evening"
            )

        st.divider()

        # Day-of-week demand chart
        dow_all = (
            sales_df.groupby(["machine", "_dow"])["total_qty"].mean().reset_index()
        )
        dow_all["day"] = dow_all["_dow"].map(dow_labels)
        fig_dow2 = px.bar(
            dow_all.sort_values("_dow"), x="day", y="total_qty", color="machine",
            barmode="group",
            title="Avg Units Sold by Day of Week (basis for time recommendations)",
            category_orders={"day": list(dow_labels.values())},
            color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C"],
        )
        fig_dow2.update_layout(xaxis_title="", yaxis_title="Avg Units Sold")
        st.plotly_chart(fig_dow2, use_container_width=True)

    st.divider()

    # ---- 7c. Stock-out root cause ----
    st.subheader("💸 Stock-out Root Cause — Lost Revenue Analysis")
    st.caption(
        "Products with both high demand AND frequent stock-outs are costing you the most. "
        "Lost revenue is estimated as: stockout events × avg units/day × unit price."
    )

    if not stockout_df.empty and "product_name" in stockout_df.columns:
        # Avg daily sales rate + price per product
        prod_stats = (
            sales_df.groupby("product_name")
            .agg(
                avg_daily_qty=("total_qty", lambda x: x.sum() / sales_df["date"].nunique()),
                unit_price=("price", "mean"),
            )
            .reset_index()
        )

        so_freq = (
            stockout_df.groupby("product_name").size().reset_index(name="stockout_events")
        )

        lost = so_freq.merge(prod_stats, on="product_name", how="left")
        lost["avg_daily_qty"] = lost["avg_daily_qty"].fillna(0)
        lost["unit_price"] = lost["unit_price"].fillna(0)
        # Assume each stockout event means ~1 day of lost sales for that product
        lost["est_lost_revenue"] = (
            lost["stockout_events"] * lost["avg_daily_qty"] * lost["unit_price"]
        ).round(0)
        lost = lost.sort_values("est_lost_revenue", ascending=False)

        lc1, lc2 = st.columns(2)
        with lc1:
            fig_lost = px.bar(
                lost.head(15).sort_values("est_lost_revenue"),
                x="est_lost_revenue", y="product_name", orientation="h",
                title="Top 15 Products by Estimated Lost Revenue",
                color_discrete_sequence=[ACCENT],
            )
            fig_lost.update_layout(xaxis_title="Est. Lost Revenue (₹)", yaxis_title="")
            st.plotly_chart(fig_lost, use_container_width=True)

        with lc2:
            fig_freq = px.bar(
                lost.sort_values("stockout_events", ascending=False).head(15).sort_values("stockout_events"),
                x="stockout_events", y="product_name", orientation="h",
                title="Top 15 Products by Stock-out Frequency",
                color_discrete_sequence=[PRIMARY],
            )
            fig_freq.update_layout(xaxis_title="Stock-out Events", yaxis_title="")
            st.plotly_chart(fig_freq, use_container_width=True)

        # Quadrant table: high freq + high lost revenue = most critical
        lost["priority"] = lost.apply(
            lambda r: "🔴 Critical" if r["stockout_events"] >= lost["stockout_events"].quantile(0.75)
                        and r["est_lost_revenue"] >= lost["est_lost_revenue"].quantile(0.75)
                      else ("🟠 Watch" if r["stockout_events"] >= lost["stockout_events"].median()
                            else "🟢 Low"),
            axis=1,
        )
        st.dataframe(
            lost[["product_name", "stockout_events", "avg_daily_qty", "unit_price", "est_lost_revenue", "priority"]]
            .rename(columns={
                "product_name": "Product",
                "stockout_events": "Stock-out Events",
                "avg_daily_qty": "Avg Daily Qty Sold",
                "unit_price": "Unit Price (₹)",
                "est_lost_revenue": "Est. Lost Revenue (₹)",
                "priority": "Priority",
            })
            .sort_values("Est. Lost Revenue (₹)", ascending=False),
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "🔴 Critical = frequent stockouts AND high revenue impact. Fix these first. "
            "Est. lost revenue assumes each stockout event costs one full day of average sales for that product."
        )
    else:
        st.info("No stock-out data available.")

# ============================================================
# 8. INVENTORY & STOCK TAB
# ============================================================
with tab_inv:
    no_stock_in = stock_in_df.empty
    no_inventory = inventory_df.empty

    if no_stock_in and no_inventory:
        st.info(
            "No inventory data loaded. Add `stock_in` and `inventory` GIDs under "
            "`[gids]` in your Streamlit secrets to enable this tab."
        )
        st.stop()

    # ---- 8a. KPI row ----
    st.subheader("📊 Warehouse Snapshot")

    inv_kpi = st.columns(5)

    if not no_inventory:
        latest_inv = (
            inventory_df.sort_values("date")
            .groupby("product_name")
            .last()
            .reset_index()
        )
        total_warehouse = latest_inv["final_in_warehouse"].sum()
        products_tracked = len(latest_inv)
        zero_stock = (latest_inv["final_in_warehouse"] <= 0).sum()
        has_warning = latest_inv["warning_note"].astype(str).str.strip().replace("nan", "").ne("").sum() if "warning_note" in latest_inv.columns else 0
    else:
        total_warehouse = products_tracked = zero_stock = has_warning = 0

    if not no_stock_in:
        total_packets = stock_in_df["packets_added"].sum()
        unknown_pct = (
            stock_in_df["is_unknown_product"].astype(str).str.lower().isin(["true", "1", "yes"]).sum()
            / max(len(stock_in_df), 1) * 100
        ) if "is_unknown_product" in stock_in_df.columns else 0
    else:
        total_packets = unknown_pct = 0

    inv_kpi[0].metric("Total Units in Warehouse", f"{total_warehouse:,.0f}")
    inv_kpi[1].metric("Products Tracked", f"{products_tracked:,}")
    inv_kpi[2].metric("Zero-stock Products", f"{zero_stock:,}", delta=f"-{zero_stock}" if zero_stock else None, delta_color="inverse")
    inv_kpi[3].metric("Total Packets Received", f"{total_packets:,.0f}")
    inv_kpi[4].metric("Unknown Product Entries", f"{unknown_pct:.1f}%", help="% of Stock In Log entries flagged is_unknown_product")

    st.divider()

    # ---- 8a-ii. Data quality flags ----
    if not no_inventory:
        _neg_stock = latest_inv[latest_inv["final_in_warehouse"] < 0].copy()
    else:
        _neg_stock = pd.DataFrame()

    _unknown_si = pd.DataFrame()
    if not no_stock_in and "is_unknown_product" in stock_in_df.columns:
        _unknown_si = stock_in_df[
            stock_in_df["is_unknown_product"].astype(str).str.lower().isin(["true", "1", "yes"])
        ]

    if not _neg_stock.empty or not _unknown_si.empty:
        with st.expander(
            f"🔧 Data Quality Issues — {len(_neg_stock)} negative-stock products, "
            f"{len(_unknown_si)} unknown stock-in entries",
            expanded=True,
        ):
            st.caption(
                "Negative warehouse quantities almost always mean a **product name mismatch**: "
                "stock was dispatched or sold under one spelling, but received or counted under "
                "a different spelling. Add the variant name to your canonical name map to fix the "
                "accounting. Unknown stock-in entries have the same root cause — the name on the "
                "inbound delivery couldn't be matched to any known product."
            )
            if not _neg_stock.empty:
                st.markdown("**Products with negative warehouse quantity (name mapping needed):**")
                _neg_display_cols = [c for c in [
                    "product_name", "final_in_warehouse", "refilling_quantity", "new_stock_added"
                ] if c in _neg_stock.columns]
                st.dataframe(
                    _neg_stock[_neg_display_cols].rename(columns={
                        "product_name": "Product (check spelling)",
                        "final_in_warehouse": "Final in Warehouse",
                        "refilling_quantity": "Last Dispatched",
                        "new_stock_added": "Last Stock Added",
                    }).sort_values("Final in Warehouse"),
                    use_container_width=True, hide_index=True,
                )
            if not _unknown_si.empty:
                st.markdown("**Unknown product entries in Stock In Log (name mapping needed):**")
                _unk_cols = [c for c in ["date", "raw_name", "packets_added"] if c in _unknown_si.columns]
                st.dataframe(
                    _unknown_si[_unk_cols].sort_values("date", ascending=False),
                    use_container_width=True, hide_index=True,
                )

    st.divider()

    # ---- 8b. Latest-day detail ----
    if not no_inventory:
        latest_date = inventory_df["date"].dropna().max().date()
        latest_day_df = inventory_df[inventory_df["date"].dt.date == latest_date].copy()

        st.subheader(f"📅 Latest Inventory Snapshot — {latest_date.strftime('%d %b %Y')}")
        st.caption("Full per-product breakdown for the most recent date in the Inventory Log.")

        ld_c1, ld_c2, ld_c3, ld_c4 = st.columns(4)
        ld_c1.metric("Products Recorded", len(latest_day_df))
        ld_c2.metric("Total in Warehouse", f"{latest_day_df['final_in_warehouse'].sum():,.0f}")
        ld_c3.metric("Dispatched to Machines", f"{latest_day_df['refilling_quantity'].sum():,.0f}")
        ld_c4.metric("New Stock Added", f"{latest_day_df['new_stock_added'].sum():,.0f}")

        ld_col1, ld_col2 = st.columns(2)

        with ld_col1:
            fig_ld_wh = px.bar(
                latest_day_df.sort_values("final_in_warehouse", ascending=True),
                x="final_in_warehouse", y="product_name", orientation="h",
                title="Warehouse Units per Product",
                color_discrete_sequence=[PRIMARY],
            )
            fig_ld_wh.update_layout(xaxis_title="Units", yaxis_title="", height=max(300, len(latest_day_df) * 22))
            st.plotly_chart(fig_ld_wh, use_container_width=True)

        with ld_col2:
            fig_ld_flow = px.bar(
                latest_day_df.sort_values("refilling_quantity", ascending=True),
                x="refilling_quantity", y="product_name", orientation="h",
                title="Dispatched to Machines per Product",
                color_discrete_sequence=[ACCENT],
            )
            fig_ld_flow.update_layout(xaxis_title="Units", yaxis_title="", height=max(300, len(latest_day_df) * 22))
            st.plotly_chart(fig_ld_flow, use_container_width=True)

        # Full detail table
        display_cols = [c for c in [
            "product_name", "physical_count_yesterday_evening", "new_stock_added",
            "refilling_quantity", "final_in_warehouse", "units", "warning_note",
        ] if c in latest_day_df.columns]
        col_rename = {
            "product_name": "Product",
            "physical_count_yesterday_evening": "Physical Count (eve)",
            "new_stock_added": "New Stock Added",
            "refilling_quantity": "Dispatched to Machines",
            "final_in_warehouse": "Final in Warehouse",
            "units": "Units/Packet",
            "warning_note": "Warning",
        }
        latest_day_display = latest_day_df[display_cols].rename(columns=col_rename).sort_values(
            "Final in Warehouse", ascending=False
        )
        st.dataframe(latest_day_display, use_container_width=True, hide_index=True)

        st.divider()

    # ---- 8c. Warehouse levels (all-time latest per product) ----
    if not no_inventory:
        st.subheader("🏪 Current Warehouse Levels")

        col_wh1, col_wh2 = st.columns((3, 2))

        with col_wh1:
            top_wh = latest_inv.sort_values("final_in_warehouse", ascending=False).head(20)
            fig_wh = px.bar(
                top_wh.sort_values("final_in_warehouse"),
                x="final_in_warehouse", y="product_name", orientation="h",
                title="Top 20 Products by Units in Warehouse",
                color_discrete_sequence=[PRIMARY],
            )
            fig_wh.update_layout(xaxis_title="Units", yaxis_title="", height=500)
            st.plotly_chart(fig_wh, use_container_width=True)

        with col_wh2:
            # Days of cover: warehouse units / avg daily sales rate
            avg_daily = (
                sales_df.groupby("product_name")["total_qty"]
                .sum()
                .div(max(sales_df["date"].dt.date.nunique(), 1))
                .reset_index()
                .rename(columns={"total_qty": "avg_daily_qty"})
            )
            cover = latest_inv.merge(avg_daily, on="product_name", how="left")
            cover["avg_daily_qty"] = cover["avg_daily_qty"].fillna(0)
            cover["days_of_cover"] = cover.apply(
                lambda r: r["final_in_warehouse"] / r["avg_daily_qty"]
                if r["avg_daily_qty"] > 0 else np.inf,
                axis=1,
            )
            cover["cover_label"] = cover["days_of_cover"].apply(
                lambda d: "🔴 <3d" if d < 3 else ("🟠 3–7d" if d < 7 else "🟢 7d+")
            )

            cover_summary = cover["cover_label"].value_counts().reset_index()
            cover_summary.columns = ["Status", "Products"]
            fig_cover = px.pie(
                cover_summary, names="Status", values="Products",
                title="Days of Cover Distribution",
                hole=0.5,
                color="Status",
                color_discrete_map={"🔴 <3d": "#B85C5C", "🟠 3–7d": ACCENT, "🟢 7d+": PRIMARY},
            )
            st.plotly_chart(fig_cover, use_container_width=True)

            urgent = cover[cover["days_of_cover"] < 3].sort_values("days_of_cover")
            if not urgent.empty:
                st.markdown("**⚠️ Restock urgently (< 3 days cover):**")
                st.dataframe(
                    urgent[["product_name", "final_in_warehouse", "avg_daily_qty", "days_of_cover"]]
                    .rename(columns={
                        "product_name": "Product",
                        "final_in_warehouse": "In Warehouse",
                        "avg_daily_qty": "Avg Daily Sales",
                        "days_of_cover": "Days Left",
                    })
                    .assign(**{"Days Left": lambda df: df["Days Left"].round(1)}),
                    use_container_width=True, hide_index=True,
                )

        st.divider()

        # ---- 8c-ii. Predictions cross-reference ----
        st.subheader("🔮 Predictions Cross-reference")
        st.caption(
            "Compares the **actual warehouse count** (from the Inventory Log) against the "
            "**estimated stock level** computed in the Predictions tab (last refill qty − units "
            "sold since). Large gaps indicate name mismatches, unrecorded dispatches, or "
            "refill data that's out of date. Urgency and suggested order are at the 14-day "
            "default rate — go to the Predictions tab to adjust assumptions."
        )

        if not _default_stock_table.empty:
            _xref = latest_inv[["product_name", "final_in_warehouse"]].merge(
                _default_stock_table[["product_name", "current_stock_est", "daily_sales_rate", "days_remaining", "urgency"]],
                on="product_name", how="outer",
            )
            _xref["gap"] = _xref["final_in_warehouse"].fillna(0) - _xref["current_stock_est"].fillna(0)
            _xref["gap_flag"] = _xref["gap"].apply(
                lambda g: "🔴 Large gap" if abs(g) > 20 else ("🟠 Minor gap" if abs(g) > 5 else "🟢 OK")
            )
            _xref["days_remaining"] = _xref["days_remaining"].apply(
                lambda d: f"{d:.1f}d" if np.isfinite(d) else "∞"
            )
            st.dataframe(
                _xref.rename(columns={
                    "product_name": "Product",
                    "final_in_warehouse": "Actual Warehouse",
                    "current_stock_est": "Predicted Stock",
                    "gap": "Gap (Actual − Predicted)",
                    "gap_flag": "Gap Status",
                    "daily_sales_rate": "Daily Sales Rate",
                    "days_remaining": "Days Remaining",
                    "urgency": "Urgency",
                }).sort_values("Gap (Actual − Predicted)"),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("Predictions data not available — make sure your Refilling sheet has product_id, product_name, and qty_after_refill columns.")

        st.divider()

        # ---- 8d. Inventory flow over time ----
        st.subheader("🔄 Daily Inventory Flow")
        st.caption("New stock added vs units dispatched to machines (refilling quantity), per day.")

        if "new_stock_added" in inventory_df.columns:
            _inv_in = inventory_df.groupby(inventory_df["date"].dt.date)["new_stock_added"].sum()
            snapshot_row("Daily New Stock Received (units)", period_avgs(_inv_in), fmt="{:,.0f}")
        if "refilling_quantity" in inventory_df.columns:
            _inv_out = inventory_df.groupby(inventory_df["date"].dt.date)["refilling_quantity"].sum()
            snapshot_row("Daily Dispatched to Machines (units)", period_avgs(_inv_out), fmt="{:,.0f}")
        st.divider()

        daily_flow = (
            inventory_df.groupby(inventory_df["date"].dt.date)[["new_stock_added", "refilling_quantity"]]
            .sum().reset_index()
        )
        daily_flow.columns = ["date", "new_stock_added", "refilling_quantity"]
        daily_flow_m = daily_flow.melt(id_vars="date", var_name="flow_type", value_name="units")
        daily_flow_m["flow_type"] = daily_flow_m["flow_type"].map(
            {"new_stock_added": "New Stock Received", "refilling_quantity": "Dispatched to Machines"}
        )

        fig_flow = px.bar(
            daily_flow_m, x="date", y="units", color="flow_type", barmode="group",
            title="Stock In vs Machine Dispatch per Day",
            color_discrete_map={"New Stock Received": PRIMARY, "Dispatched to Machines": ACCENT},
        )
        fig_flow.update_layout(xaxis_title="", yaxis_title="Units", legend_title="")
        st.plotly_chart(fig_flow, use_container_width=True)

        # Net warehouse change
        daily_flow["net_change"] = daily_flow["new_stock_added"] - daily_flow["refilling_quantity"]
        fig_net = px.bar(
            daily_flow, x="date", y="net_change",
            title="Net Warehouse Change per Day (positive = building stock, negative = drawing down)",
            color_discrete_sequence=[PRIMARY],
        )
        fig_net.update_layout(xaxis_title="", yaxis_title="Net Units")
        fig_net.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_net, use_container_width=True)

        st.divider()

        # ---- 8e. Warning flags ----
        if "warning_note" in inventory_df.columns:
            warned = (
                inventory_df[
                    inventory_df["warning_note"].astype(str).str.strip().replace("nan", "").ne("")
                ]
                .sort_values("date", ascending=False)
            )
            if not warned.empty:
                st.subheader("⚠️ Products with Warning Notes")
                st.dataframe(
                    warned[["date", "product_name", "final_in_warehouse", "warning_note"]]
                    .rename(columns={
                        "date": "Date",
                        "product_name": "Product",
                        "final_in_warehouse": "Warehouse Units",
                        "warning_note": "Warning",
                    }),
                    use_container_width=True, hide_index=True,
                )
                st.divider()

    # ---- 8f. Stock In Log ----
    if not no_stock_in:
        st.subheader("📥 Stock In Log — Inbound Trends")

        si_c1, si_c2 = st.columns(2)

        with si_c1:
            daily_si = (
                stock_in_df.groupby(stock_in_df["date"].dt.date)["packets_added"]
                .sum().reset_index()
            )
            daily_si.columns = ["date", "packets_added"]
            fig_si = px.bar(
                daily_si, x="date", y="packets_added",
                title="Packets Received per Day",
                color_discrete_sequence=[PRIMARY],
            )
            fig_si.update_layout(xaxis_title="", yaxis_title="Packets")
            st.plotly_chart(fig_si, use_container_width=True)

        with si_c2:
            top_si = (
                stock_in_df.groupby("product_name")["packets_added"]
                .sum().sort_values(ascending=False).head(15).reset_index()
            )
            fig_si2 = px.bar(
                top_si.sort_values("packets_added"),
                x="packets_added", y="product_name", orientation="h",
                title="Top 15 Products by Packets Received",
                color_discrete_sequence=[ACCENT],
            )
            fig_si2.update_layout(xaxis_title="Packets", yaxis_title="")
            st.plotly_chart(fig_si2, use_container_width=True)

        # Receive rate vs sales rate (turnover proxy)
        if not no_inventory:
            st.subheader("⚖️ Stock Received vs Sold — Inventory Turnover Proxy")
            st.caption(
                "Products far above the diagonal are accumulating stock; "
                "below it means demand is outpacing inbound supply."
            )
            si_totals = (
                stock_in_df.groupby("product_name")["packets_added"].sum().reset_index()
                .rename(columns={"packets_added": "total_received"})
            )
            sales_totals = (
                sales_df.groupby("product_name")["total_qty"].sum().reset_index()
                .rename(columns={"total_qty": "total_sold"})
            )
            turnover = si_totals.merge(sales_totals, on="product_name", how="inner")
            turnover = turnover[turnover["total_sold"] > 0]

            if not turnover.empty:
                fig_turn = px.scatter(
                    turnover, x="total_sold", y="total_received",
                    text="product_name",
                    title="Stock Received vs Units Sold",
                    color_discrete_sequence=[PRIMARY],
                )
                max_val = max(turnover["total_sold"].max(), turnover["total_received"].max()) * 1.1
                fig_turn.add_shape(
                    type="line", x0=0, y0=0, x1=max_val, y1=max_val,
                    line=dict(color="gray", dash="dash"),
                )
                fig_turn.update_traces(textposition="top center")
                fig_turn.update_layout(xaxis_title="Total Units Sold", yaxis_title="Total Packets Received")
                st.plotly_chart(fig_turn, use_container_width=True)

        # Unknown products
        if "is_unknown_product" in stock_in_df.columns:
            unknown = stock_in_df[
                stock_in_df["is_unknown_product"].astype(str).str.lower().isin(["true", "1", "yes"])
            ]
            if not unknown.empty:
                st.subheader("❓ Unknown Product Entries in Stock In Log")
                st.caption("These entries couldn't be matched to a known product — worth cleaning up for accurate tracking.")
                st.dataframe(
                    unknown[["date", "raw_name", "packets_added"]].sort_values("date", ascending=False),
                    use_container_width=True, hide_index=True,
                )
# ============================================================
# 9. VERKA TAB
# ============================================================
with tab_verka:
    VERKA = "Verka"

    # Filter all datasets to Verka only (case-insensitive)
    vk_sales = sales_f[sales_f["brand_name"].str.strip().str.lower() == VERKA.lower()] if "brand_name" in sales_f.columns else pd.DataFrame()
    vk_refill = refill_f[refill_f["brand_name"].str.strip().str.lower() == VERKA.lower()] if "brand_name" in refill_f.columns else pd.DataFrame()
    vk_stockout = stockout_f[stockout_f["product_name"].isin(vk_sales["product_name"].unique())] if not vk_sales.empty and "product_name" in stockout_f.columns else pd.DataFrame()
    vk_stock = _default_stock_table[_default_stock_table["brand_name"].str.strip().str.lower() == VERKA.lower()] if not _default_stock_table.empty and "brand_name" in _default_stock_table.columns else pd.DataFrame()

    if vk_sales.empty and vk_refill.empty:
        st.info("No Verka products found in the current data. Check that brand_name is set to 'Verka' in your sheets.")
        st.stop()

    # ── MACRO: KPI row ──────────────────────────────────────────────────────────
    st.subheader("🥛 Verka — Brand Overview")

    vk_total_sales = vk_sales["total_sales"].sum() if "total_sales" in vk_sales.columns else 0
    vk_total_qty   = vk_sales["total_qty"].sum() if "total_qty" in vk_sales.columns else 0
    vk_products    = vk_sales["product_name"].nunique() if "product_name" in vk_sales.columns else 0
    vk_so_count    = len(vk_stockout)
    vk_refill_val  = vk_refill["amount"].sum() if "amount" in vk_refill.columns else 0
    _all_sales_tot = sales_f["total_sales"].sum() if "total_sales" in sales_f.columns else 1
    vk_share       = vk_total_sales / _all_sales_tot * 100 if _all_sales_tot else 0

    vk_k1, vk_k2, vk_k3, vk_k4, vk_k5, vk_k6 = st.columns(6)
    vk_k1.metric("Verka Revenue",        f"₹{vk_total_sales:,.0f}")
    vk_k2.metric("Units Sold",           f"{vk_total_qty:,.0f}")
    vk_k3.metric("Products",             f"{vk_products}")
    vk_k4.metric("Share of Total Sales", f"{vk_share:.1f}%")
    vk_k5.metric("Stock-out Events",     f"{vk_so_count}")
    vk_k6.metric("Total Refill Value",   f"₹{vk_refill_val:,.0f}")

    st.divider()

    # ── MACRO: Daily snapshot strips ───────────────────────────────────────────
    if not vk_sales.empty and "total_sales" in vk_sales.columns:
        snapshot_row("Verka — Daily Sales (₹)", period_avgs(vk_sales.groupby(vk_sales["date"].dt.date)["total_sales"].sum()))
    if not vk_sales.empty and "total_qty" in vk_sales.columns:
        snapshot_row("Verka — Daily Units Sold", period_avgs(vk_sales.groupby(vk_sales["date"].dt.date)["total_qty"].sum()), fmt="{:,.0f}")

    st.divider()

    # ── MACRO: Sales trend + machine split ─────────────────────────────────────
    vk_mc1, vk_mc2 = st.columns((2, 1))
    with vk_mc1:
        _vk_trend = vk_sales.groupby(vk_sales["date"].dt.date)["total_sales"].sum().reset_index()
        _vk_trend.columns = ["date", "total_sales"]
        fig_vk_trend = px.area(_vk_trend, x="date", y="total_sales",
                               title="Verka Daily Sales Trend",
                               color_discrete_sequence=[PRIMARY])
        fig_vk_trend.update_layout(xaxis_title="", yaxis_title="Sales (₹)")
        st.plotly_chart(fig_vk_trend, use_container_width=True)

    with vk_mc2:
        if "machine" in vk_sales.columns:
            _vk_by_machine = vk_sales.groupby("machine")["total_sales"].sum().reset_index()
            fig_vk_pie = px.pie(_vk_by_machine, names="machine", values="total_sales",
                                title="Verka Sales by Machine", hole=0.5,
                                color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C"])
            st.plotly_chart(fig_vk_pie, use_container_width=True)

    st.divider()

    # ── MESO: Per-product revenue & units ──────────────────────────────────────
    st.subheader("📦 Verka Products — Sales Breakdown")

    vk_mp1, vk_mp2 = st.columns(2)
    with vk_mp1:
        _vk_prod_rev = vk_sales.groupby("product_name")["total_sales"].sum().sort_values(ascending=False).reset_index()
        fig_vk_prod = px.bar(_vk_prod_rev.sort_values("total_sales"),
                             x="total_sales", y="product_name", orientation="h",
                             title="Revenue by Product", color_discrete_sequence=[PRIMARY])
        fig_vk_prod.update_layout(xaxis_title="Sales (₹)", yaxis_title="")
        st.plotly_chart(fig_vk_prod, use_container_width=True)

    with vk_mp2:
        _vk_prod_qty = vk_sales.groupby("product_name")["total_qty"].sum().sort_values(ascending=False).reset_index()
        fig_vk_qty = px.bar(_vk_prod_qty.sort_values("total_qty"),
                            x="total_qty", y="product_name", orientation="h",
                            title="Units Sold by Product", color_discrete_sequence=[ACCENT])
        fig_vk_qty.update_layout(xaxis_title="Units", yaxis_title="")
        st.plotly_chart(fig_vk_qty, use_container_width=True)

    # Product trend lines
    _vk_prod_trend = vk_sales.groupby(["product_name", vk_sales["date"].dt.date])["total_sales"].sum().reset_index()
    _vk_prod_trend.columns = ["product_name", "date", "total_sales"]
    fig_vk_lines = px.line(_vk_prod_trend, x="date", y="total_sales",
                           color="product_name", markers=False,
                           title="Product Sales Trends Over Time")
    fig_vk_lines.update_layout(xaxis_title="", yaxis_title="Sales (₹)", legend_title="Product")
    st.plotly_chart(fig_vk_lines, use_container_width=True)

    # Per-product D-1/D-2/avg table
    st.caption("**Per-product daily snapshot**")
    _vk_ref_avgs = period_avgs(vk_sales.groupby(vk_sales["date"].dt.date)["total_sales"].sum())
    _vk_lat = _vk_ref_avgs["date_latest"].strftime("%-d %b") if _vk_ref_avgs["date_latest"] else "Latest"
    _vk_m1  = (_vk_ref_avgs["date_m1"].strftime("%-d %b") + " (D−1)") if _vk_ref_avgs["date_m1"] else "D−1"
    _vk_m2  = (_vk_ref_avgs["date_m2"].strftime("%-d %b") + " (D−2)") if _vk_ref_avgs["date_m2"] else "D−2"

    _vk_prod_rows = []
    for _prod in sorted(vk_sales["product_name"].dropna().unique()):
        _ps = vk_sales[vk_sales["product_name"] == _prod].groupby(vk_sales["date"].dt.date)["total_sales"].sum()
        _pa = period_avgs(_ps)
        _d  = _pa["latest"] - _pa["day_m1"]
        _dpct = f"{'▲' if _d >= 0 else '▼'} {abs(_d / _pa['day_m1'] * 100):.0f}%" if _pa["day_m1"] else "—"
        _vk_prod_rows.append({
            "Product": _prod,
            _vk_lat: f"₹{_pa['latest']:,.0f}",
            _vk_m1:  f"₹{_pa['day_m1']:,.0f}",
            _vk_m2:  f"₹{_pa['day_m2']:,.0f}",
            "Δ":           _dpct,
            "Avg 3d":      f"₹{_pa['avg_3d']:,.0f}",
            "Avg 7d":      f"₹{_pa['avg_7d']:,.0f}",
            "Avg 15d":     f"₹{_pa['avg_15d']:,.0f}",
            "Overall/Day": f"₹{_pa['avg_all']:,.0f}",
        })
    st.dataframe(pd.DataFrame(_vk_prod_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── MESO: Product × Machine matrix ─────────────────────────────────────────
    if "machine" in vk_sales.columns:
        st.subheader("🔀 Product × Machine Matrix")
        _vk_matrix = (
            vk_sales.groupby(["product_name", "machine"])["total_sales"]
            .sum().unstack(fill_value=0)
        )
        _vk_matrix["Total"] = _vk_matrix.sum(axis=1)
        _vk_matrix = _vk_matrix.sort_values("Total", ascending=False).drop(columns="Total")
        st.dataframe(
            _vk_matrix.style.format("₹{:,.0f}").background_gradient(cmap="Greens", axis=None),
            use_container_width=True,
        )

        _vk_pm = vk_sales.groupby(["machine", "product_name"])["total_sales"].sum().reset_index()
        fig_vk_pm = px.bar(_vk_pm, x="machine", y="total_sales", color="product_name",
                           title="Revenue per Machine (stacked by product)", barmode="stack")
        fig_vk_pm.update_layout(xaxis_title="", yaxis_title="Sales (₹)", legend_title="Product")
        st.plotly_chart(fig_vk_pm, use_container_width=True)

        st.divider()

    # ── MICRO: Stock & refill status ────────────────────────────────────────────
    st.subheader("📊 Verka — Stock & Refill Status")

    if not vk_stock.empty:
        _vk_sd = vk_stock.copy()
        _vk_sd["days_remaining"] = _vk_sd["days_remaining"].apply(lambda d: f"{d:.1f}d" if np.isfinite(d) else "∞")
        st.dataframe(
            _vk_sd[[c for c in ["product_name","last_refill_date","current_stock_est",
                                 "daily_sales_rate","days_remaining","urgency"] if c in _vk_sd.columns]]
            .rename(columns={"product_name":"Product","last_refill_date":"Last Refill",
                              "current_stock_est":"Est. Stock","daily_sales_rate":"Daily Sales Rate",
                              "days_remaining":"Days Remaining","urgency":"Urgency"})
            .sort_values("Est. Stock"),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No refill data for Verka — check that brand_name is populated in the Refilling sheet.")

    if not vk_refill.empty and "refill_qty" in vk_refill.columns:
        _vk_ref_daily_s = vk_refill.groupby(vk_refill["date"].dt.date)["refill_qty"].sum()
        if not _vk_ref_daily_s.empty:
            snapshot_row("Verka — Daily Units Refilled", period_avgs(_vk_ref_daily_s), fmt="{:,.0f}")

        _vk_rfp = vk_refill.groupby("product_name")["refill_qty"].sum().sort_values(ascending=False).reset_index()
        if not _vk_rfp.empty:
            fig_vk_rf = px.bar(_vk_rfp.sort_values("refill_qty"),
                               x="refill_qty", y="product_name", orientation="h",
                               title="Units Refilled by Product", color_discrete_sequence=[PRIMARY])
            fig_vk_rf.update_layout(xaxis_title="Units Refilled", yaxis_title="")
            st.plotly_chart(fig_vk_rf, use_container_width=True)

    st.divider()

    # ── MICRO: Stock-out analysis ───────────────────────────────────────────────
    st.subheader("🚫 Verka — Stock-out Analysis")
    if not vk_stockout.empty:
        _vk_so1, _vk_so2 = st.columns(2)
        with _vk_so1:
            _vk_so_freq = vk_stockout["product_name"].value_counts().reset_index()
            _vk_so_freq.columns = ["product_name", "events"]
            fig_vk_so = px.bar(_vk_so_freq.sort_values("events"),
                               x="events", y="product_name", orientation="h",
                               title="Stock-out Frequency by Product",
                               color_discrete_sequence=[ACCENT])
            fig_vk_so.update_layout(xaxis_title="Events", yaxis_title="")
            st.plotly_chart(fig_vk_so, use_container_width=True)

        with _vk_so2:
            _vk_so_d = vk_stockout.groupby(vk_stockout["date"].dt.date).size().reset_index(name="events")
            fig_vk_so2 = px.bar(_vk_so_d, x="date", y="events",
                                title="Verka Stock-outs Over Time",
                                color_discrete_sequence=[PRIMARY])
            fig_vk_so2.update_layout(xaxis_title="", yaxis_title="Events")
            st.plotly_chart(fig_vk_so2, use_container_width=True)

        st.dataframe(vk_stockout.sort_values("date", ascending=False),
                     use_container_width=True, hide_index=True)
    else:
        st.success("No stock-out events for Verka in this date range. 🎉")

    st.divider()

    # ── MICRO: Full transaction log ─────────────────────────────────────────────
    with st.expander("📋 Full Verka Sales Log"):
        st.dataframe(vk_sales.sort_values("date", ascending=False),
                     use_container_width=True, hide_index=True)
