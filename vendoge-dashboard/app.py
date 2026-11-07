"""
Vendoge Operations Dashboard
-----------------------------
Reads live data from a public Google Sheet of pre-aggregated machine/revenue
analytics tables (Machines, Txn_Daily, Txn_Hourly, Txn_Failures, Txn_Product,
Metrics_Summary, Rev_DoD, Rev_MoM, Refill_Hourly, Refill_Product,
SKU_Category_Map, SKU_Mix) and renders an interactive Streamlit dashboard.

Configure the sheet ID in Streamlit secrets (see README.md):

[sheets]
dashboard = "YOUR_GOOGLE_SHEET_ID"
"""

from datetime import timedelta
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st

PRIMARY = "#0E6E55"      # deep teal — vending green
ACCENT = "#F2A93B"       # warm amber — restock/alert accent
PALETTE = [PRIMARY, ACCENT, "#6C8EBF", "#B85C5C", "#6B5CA5", "#4F8A3D",
           "#C98A3B", "#3B8A8C", "#A8556C", "#7A8C3B", "#555B6E"]

st.set_page_config(
    page_title="Vendoge Dashboard",
    page_icon="🥤",
    layout="wide",
)

# ============================================================
# 1. CONFIG — loaded from Streamlit secrets
# ============================================================
try:
    SHEET_ID = st.secrets["sheets"]["dashboard"]
except (KeyError, FileNotFoundError):
    st.error(
        "Missing secrets! This app needs `[sheets]` with a `dashboard` sheet ID "
        "set up in Streamlit secrets — locally in `.streamlit/secrets.toml`, or "
        "on Streamlit Cloud under your app's Settings > Secrets."
    )
    st.stop()

# Accounts ledger lives in a separate sheet, unrelated to the vending-sales
# data above, and backs the Accounts/HR tabs. It's optional — those tabs
# just show an info message if it isn't configured.
ACCOUNTS_SHEET_ID = st.secrets.get("sheets", {}).get("accounts")
ACCOUNTS_GID = str(st.secrets.get("gids", {}).get("accounts", {}).get("accounts", "")) if ACCOUNTS_SHEET_ID else ""

SHEET_NAMES = {
    "machines": "Machines",
    "warehouse_products": "Warehouse_Products",
    "txn_daily": "Txn_Daily",
    "txn_hourly": "Txn_Hourly",
    "txn_failures": "Txn_Failures",
    "txn_product": "Txn_Product",
    "metrics_summary": "Metrics_Summary",
    "rev_dod": "Rev_DoD",
    "rev_mom": "Rev_MoM",
    "refill_hourly": "Refill_Hourly",
    "refill_product": "Refill_Product",
    "sku_category_map": "SKU_Category_Map",
    "sku_mix": "SKU_Mix",
}

# ============================================================
# 2. DATA LOADING — pulls each named tab of a PUBLIC google sheet by name
# ============================================================


def _gviz_csv_url(sheet_name: str) -> str:
    """Build the CSV export URL for one named tab of a public Google Sheet."""
    return (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(sheet_name)}"
    )


def _read_sheet(sheet_name: str) -> pd.DataFrame:
    try:
        return pd.read_csv(_gviz_csv_url(sheet_name))
    except Exception:
        return pd.DataFrame()


def _accounts_csv_url(gid: str) -> str:
    """Build the raw CSV export URL for one tab of the (separate) accounts sheet, by gid."""
    return f"https://docs.google.com/spreadsheets/d/{ACCOUNTS_SHEET_ID}/export?format=csv&gid={gid}"


def _load_accounts() -> pd.DataFrame:
    if not (ACCOUNTS_SHEET_ID and ACCOUNTS_GID):
        return pd.DataFrame()
    try:
        accounts = pd.read_csv(_accounts_csv_url(ACCOUNTS_GID))
    except Exception:
        return pd.DataFrame()
    # Auto-detect and parse date column (dayfirst handles DD/MM/YY bank-export format)
    _ac_date_col = next((c for c in accounts.columns if "date" in c.lower()), None)
    if _ac_date_col:
        accounts[_ac_date_col] = pd.to_datetime(
            accounts[_ac_date_col], dayfirst=True, errors="coerce"
        )
    # Auto-detect and parse numeric columns
    _AC_NUMERIC_KEYWORDS = [
        "amount", "amt", "debit", "credit", "balance", " dr", " cr",
        "withdrawal", "deposit", "net (",
    ]
    for col in accounts.columns:
        if any(k in col.lower() for k in _AC_NUMERIC_KEYWORDS):
            accounts[col] = pd.to_numeric(
                accounts[col].astype(str).str.replace(",", "").str.replace("₹", "").str.strip(),
                errors="coerce",
            )
    return accounts


def _to_num(df: pd.DataFrame, cols) -> None:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def _to_str_id(df: pd.DataFrame, col: str) -> None:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64").astype(str)


@st.cache_data(ttl=300, show_spinner="Pulling latest data from Google Sheets...")
def load_data():
    machines = _read_sheet(SHEET_NAMES["machines"])
    warehouse_products = _read_sheet(SHEET_NAMES["warehouse_products"])
    txn_daily = _read_sheet(SHEET_NAMES["txn_daily"])
    txn_hourly = _read_sheet(SHEET_NAMES["txn_hourly"])
    txn_failures = _read_sheet(SHEET_NAMES["txn_failures"])
    txn_product = _read_sheet(SHEET_NAMES["txn_product"])
    metrics_summary = _read_sheet(SHEET_NAMES["metrics_summary"])
    rev_dod = _read_sheet(SHEET_NAMES["rev_dod"])
    rev_mom = _read_sheet(SHEET_NAMES["rev_mom"])
    refill_hourly = _read_sheet(SHEET_NAMES["refill_hourly"])
    refill_product = _read_sheet(SHEET_NAMES["refill_product"])
    sku_category_map = _read_sheet(SHEET_NAMES["sku_category_map"])
    sku_mix = _read_sheet(SHEET_NAMES["sku_mix"])

    _to_str_id(machines, "machine_id")
    for col in ("machine_status", "is_live", "city", "location", "warehouse"):
        if col in machines.columns:
            machines[col] = machines[col].astype(str).str.strip()

    for df in (txn_daily, txn_hourly, txn_failures, txn_product, refill_hourly):
        _to_str_id(df, "machine_id")

    if "date" in txn_daily.columns:
        txn_daily["date"] = pd.to_datetime(txn_daily["date"], errors="coerce")
    _to_num(txn_daily, [
        "rows_total", "sale_rows", "sale_qty", "revenue", "discount_value",
        "dispense_timeout_rows", "paid_not_dispensed_rows",
        "paid_not_dispensed_amount", "payment_failed_rows", "payment_pending_rows",
    ])

    for df, num_cols in (
        (txn_hourly, ["hour", "sale_rows", "sale_qty", "revenue"]),
        (txn_failures, ["rows", "amount"]),
        (txn_product, ["sale_qty", "revenue"]),
        (refill_hourly, ["hour", "refill_rows", "refill_qty"]),
    ):
        if "month" in df.columns:
            df["month"] = pd.to_datetime(df["month"], errors="coerce")
        _to_num(df, num_cols)

    if not rev_dod.empty:
        rev_dod["date"] = pd.to_datetime(rev_dod.get("date"), errors="coerce")
        _to_num(rev_dod, ["revenue", "prev_day_revenue", "change_abs", "change_pct"])

    if not rev_mom.empty:
        rev_mom["month_dt"] = pd.to_datetime(
            rev_mom.get("month").astype(str) + "-01", errors="coerce"
        )
        _to_num(rev_mom, [
            "days_counted", "revenue", "units", "avg_daily_revenue",
            "prev_month_revenue", "mom_change_pct", "prev_month_avg_daily",
            "mom_change_avg_daily_pct",
        ])

    if not metrics_summary.empty:
        for col in ("first_sale_date", "last_complete_date", "best_day"):
            if col in metrics_summary.columns:
                metrics_summary[col] = pd.to_datetime(metrics_summary[col], errors="coerce")
        _to_num(metrics_summary, [
            "machines_count", "days_since_first_sale", "active_sale_days",
            "total_revenue", "total_units", "mean_daily_revenue",
            "median_daily_revenue", "best_day_revenue", "avg_last_7d_revenue",
            "avg_last_30d_revenue", "total_rows", "dispense_failed_rows",
            "dispense_timeout_rows", "failure_rate_pct",
            "failed_amount_paid_not_dispensed",
        ])

    if not sku_category_map.empty:
        _to_num(sku_category_map, ["sold_qty", "revenue", "refilled_qty"])
        if not warehouse_products.empty and "name" in warehouse_products.columns:
            _to_num(warehouse_products, ["s_price", "original_price"])
            sku_category_map = sku_category_map.merge(
                warehouse_products[["name", "s_price"]].rename(
                    columns={"name": "product_name", "s_price": "current_price"}
                ),
                on="product_name", how="left",
            )

    if not sku_mix.empty:
        _to_num(sku_mix, [
            "skus_sold", "total_skus_sold", "sold_qty", "sold_qty_share_pct",
            "revenue", "revenue_share_pct", "refilled_qty", "refilled_qty_share_pct",
        ])
        sku_mix["scope_kind"] = sku_mix["scope"].apply(
            lambda s: "last_full_month" if str(s).startswith("last_full_month") else "all_time"
        )
        sku_mix["scope_month"] = sku_mix["scope"].astype(str).str.extract(
            r"last_full_month\s+(\S+)"
        )

    accounts = _load_accounts()

    return {
        "machines": machines,
        "warehouse_products": warehouse_products,
        "txn_daily": txn_daily,
        "txn_hourly": txn_hourly,
        "txn_failures": txn_failures,
        "txn_product": txn_product,
        "metrics_summary": metrics_summary,
        "rev_dod": rev_dod,
        "rev_mom": rev_mom,
        "refill_hourly": refill_hourly,
        "refill_product": refill_product,
        "sku_category_map": sku_category_map,
        "sku_mix": sku_mix,
        "accounts": accounts,
    }


try:
    data = load_data()
except Exception as e:
    st.error(
        "Couldn't load the Google Sheet. Most likely causes:\n\n"
        "1. The `dashboard` sheet ID in Streamlit secrets isn't set to your real "
        "sheet ID, or\n"
        "2. The sheet isn't shared as 'Anyone with the link can view', or\n"
        "3. One of the expected tabs "
        f"({', '.join(SHEET_NAMES.values())}) is missing or renamed."
    )
    st.caption(f"Technical detail: {e}")
    st.stop()

machines_df = data["machines"]
txn_daily_df = data["txn_daily"]
accounts_df = data["accounts"]

if txn_daily_df.empty or machines_df.empty:
    st.error(
        "The `Machines` and/or `Txn_Daily` tabs came back empty. The dashboard "
        "can't render without them — check the sheet is populated and shared."
    )
    st.stop()

# ============================================================
# 3. SIDEBAR FILTERS
# ============================================================
st.sidebar.title("🥤 Vendoge")
st.sidebar.caption("Filters")

min_date = txn_daily_df["date"].min()
max_date = txn_daily_df["date"].max()

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

all_cities = sorted(machines_df["city"].dropna().unique().tolist()) if "city" in machines_df.columns else []
city_sel = st.sidebar.multiselect("City", all_cities, default=all_cities, key="sidebar_city")

all_machine_names = sorted(machines_df["machine_name"].dropna().unique().tolist()) if "machine_name" in machines_df.columns else []
machine_sel = st.sidebar.multiselect("Machines", all_machine_names, default=all_machine_names, key="sidebar_machines")

if st.sidebar.button("🔄 Refresh data now"):
    st.cache_data.clear()
    st.session_state.pop("sidebar_city", None)
    st.session_state.pop("sidebar_machines", None)
    st.rerun()

st.sidebar.caption(f"Last pulled: {pd.Timestamp.now().strftime('%d %b %Y, %I:%M %p')}")
st.sidebar.caption("Data auto-refreshes every 5 minutes.")


def filter_dim(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the City / Machine sidebar filters to any table that carries those columns."""
    out = df
    if city_sel and "city" in out.columns:
        out = out[out["city"].isin(city_sel)]
    if machine_sel and "machine_name" in out.columns:
        out = out[out["machine_name"].isin(machine_sel)]
    return out.copy()


def filter_date(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    mask = (df[col].dt.date >= start_date) & (df[col].dt.date <= end_date)
    return df.loc[mask].copy()


def filter_month_overlap(df: pd.DataFrame, col: str = "month") -> pd.DataFrame:
    """Keep rows whose (whole) calendar month overlaps the selected date range."""
    if df.empty or col not in df.columns:
        return df
    month_end = df[col] + pd.offsets.MonthEnd(0)
    mask = (month_end.dt.date >= start_date) & (df[col].dt.date <= end_date)
    return df.loc[mask].copy()


machines_f = filter_dim(machines_df)
txn_daily_f = filter_date(filter_dim(txn_daily_df))
txn_hourly_f = filter_month_overlap(filter_dim(data["txn_hourly"]))
txn_failures_f = filter_month_overlap(filter_dim(data["txn_failures"]))
txn_product_f = filter_month_overlap(filter_dim(data["txn_product"]))
refill_hourly_f = filter_month_overlap(filter_dim(data["refill_hourly"]))

# ============================================================
# 4. HEADER + KPI ROW
# ============================================================
st.title("Vendoge Operations Dashboard")
st.caption("Live view of machine revenue, refilling, and dispense-failure trends across the fleet.")

total_revenue = txn_daily_f["revenue"].sum()
total_units = txn_daily_f["sale_qty"].sum()
active_days = txn_daily_f["date"].dt.date.nunique() or 1
avg_daily_revenue = total_revenue / active_days
active_machines = txn_daily_f["machine_id"].nunique()
_failure_rows = (
    txn_daily_f["dispense_timeout_rows"].sum()
    + txn_daily_f["paid_not_dispensed_rows"].sum()
    + txn_daily_f["payment_failed_rows"].sum()
)
_total_rows = txn_daily_f["rows_total"].sum()
failure_rate = (_failure_rows / _total_rows * 100) if _total_rows else 0.0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Revenue", f"₹{total_revenue:,.0f}")
k2.metric("Units Sold", f"{total_units:,.0f}")
k3.metric("Avg Daily Revenue", f"₹{avg_daily_revenue:,.0f}")
k4.metric("Machines in View", f"{active_machines:,}")
k5.metric("Failure Rate", f"{failure_rate:.2f}%")

st.divider()

# ============================================================
# 5. PERIOD-AVERAGE HELPERS
# ============================================================


def period_avgs(daily_series: pd.Series) -> dict:
    """
    Given a date-indexed daily Series, return the latest day value, the two
    preceding days, and per-day averages for 3-day, 7-day, 15-day windows
    and the full history. Windows are inclusive of the latest date.
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
    """Render a labelled 7-column snapshot strip with delta arrows."""
    def _delta(a, b):
        diff = a - b
        if b == 0:
            return None, "off"
        pct = diff / abs(b) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%", "inverse" if inverse else "normal"

    def _lbl(key):
        d = avgs.get(key)
        return d.strftime("%-d %b") if d else "—"

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


def _iqr_bounds(s: pd.Series):
    """Tukey's fences: outside these bounds counts as an outlier."""
    s = s.dropna()
    if len(s) < 4:
        return None, None
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def _flag(v, lower, upper):
    if v > upper:
        return "🔴 High"
    if v < lower:
        return "🔵 Low"
    return ""


LEVEL_LABELS = {"machine": "Machine", "location": "Location", "warehouse": "Warehouse"}

# ============================================================
# 6. TABS
# ============================================================
(tab_overview, tab_attention, tab_revenue, tab_refill, tab_failures, tab_sku, tab_machines,
 tab_outliers, tab_accounts, tab_hr) = st.tabs([
    "📊 Overview", "🚨 Needs Attention", "💰 Revenue & Sales", "🔁 Refilling", "🚫 Failures",
    "🧃 SKU Mix", "🖥️ Machines", "⚠️ Outliers", "💳 Accounts", "👥 HR",
])

# ---------- OVERVIEW ----------
with tab_overview:
    st.subheader("Daily Performance Snapshot")
    st.caption("How today compares to recent averages — all figures are per-day totals across the filtered fleet.")

    daily_rev = txn_daily_f.groupby(txn_daily_f["date"].dt.date)["revenue"].sum()
    daily_rev.index = pd.to_datetime(daily_rev.index)
    snapshot_row("Daily Revenue", period_avgs(daily_rev), fmt="₹{:,.0f}")

    st.divider()

    fig_rev = px.bar(
        txn_daily_f.groupby("date", as_index=False)["revenue"].sum(),
        x="date", y="revenue", title="Daily Revenue Trend",
        color_discrete_sequence=[PRIMARY],
    )
    fig_rev.update_layout(xaxis_title="", yaxis_title="Revenue (₹)")
    st.plotly_chart(fig_rev, use_container_width=True)

    st.divider()

    st.subheader("🏆 Top Performers")
    st.caption("Lifetime metrics from `Metrics_Summary` — independent of the date/city/machine filters above.")

    metrics_df = data["metrics_summary"]
    if metrics_df.empty:
        st.info("No `Metrics_Summary` data loaded.")
    else:
        tp_c1, tp_c2 = st.columns(2)
        with tp_c1:
            tp_level = st.radio("Level", list(LEVEL_LABELS), format_func=lambda k: LEVEL_LABELS[k],
                                 horizontal=True, key="ov_level")
        metric_options = {
            "total_revenue": "Total Revenue (₹)",
            "total_units": "Total Units",
            "avg_last_7d_revenue": "Avg Revenue, Last 7 Days (₹)",
            "failure_rate_pct": "Failure Rate (%)",
        }
        with tp_c2:
            tp_metric = st.selectbox("Rank by", list(metric_options), format_func=lambda k: metric_options[k], key="ov_metric")

        level_df = metrics_df[metrics_df["level"] == tp_level]
        top_n = level_df[["label", tp_metric]].dropna().sort_values(tp_metric, ascending=False).head(10)
        if top_n.empty:
            st.info("No data for this level yet.")
        else:
            fig_top = px.bar(
                top_n.sort_values(tp_metric), x=tp_metric, y="label", orientation="h",
                title=f"Top 10 {LEVEL_LABELS[tp_level]}s by {metric_options[tp_metric]}",
                color_discrete_sequence=[ACCENT],
            )
            fig_top.update_layout(xaxis_title=metric_options[tp_metric], yaxis_title="")
            st.plotly_chart(fig_top, use_container_width=True)

# ---------- NEEDS ATTENTION ----------
with tab_attention:
    st.subheader("🚨 Needs Attention")
    st.caption(
        "Per-machine health check over the most recent days of data, regardless of the "
        "date range picked in the sidebar (City/Machine filters still apply). Compares each "
        "machine's recent average to its own trailing 30-day baseline."
    )

    txn_daily_recent = filter_dim(txn_daily_df)
    latest_date = txn_daily_recent["date"].max()

    if pd.isna(latest_date):
        st.info("No transaction data available for the current City/Machine filters.")
    else:
        n_days = st.radio(
            "Look back", [1, 2, 3, 4, 5],
            format_func=lambda n: f"Last {n} day" + ("s" if n > 1 else ""),
            index=2, horizontal=True, key="attn_days",
        )
        window_start = latest_date - pd.Timedelta(days=n_days - 1)
        baseline_end = window_start - pd.Timedelta(days=1)
        baseline_start = baseline_end - pd.Timedelta(days=29)

        st.caption(
            f"Window: **{window_start.date()} → {latest_date.date()}** vs. baseline "
            f"**{baseline_start.date()} → {baseline_end.date()}** (trailing 30 days before the window)."
        )

        window_df = txn_daily_recent[
            (txn_daily_recent["date"] >= window_start) & (txn_daily_recent["date"] <= latest_date)
        ].copy()
        baseline_df = txn_daily_recent[
            (txn_daily_recent["date"] >= baseline_start) & (txn_daily_recent["date"] <= baseline_end)
        ].copy()

        for _df in (window_df, baseline_df):
            _df["failure_rows"] = (
                _df["dispense_timeout_rows"] + _df["paid_not_dispensed_rows"] + _df["payment_failed_rows"]
            )

        # ── Fleet-level KPIs ─────────────────────────────────────────────────
        win_revenue = window_df["revenue"].sum()
        win_avg_daily = win_revenue / n_days
        base_avg_daily = (
            baseline_df.groupby(baseline_df["date"].dt.date)["revenue"].sum().mean()
            if not baseline_df.empty else 0.0
        )
        win_failure_rate = (
            window_df["failure_rows"].sum() / window_df["rows_total"].sum() * 100
            if window_df["rows_total"].sum() else 0.0
        )
        win_rows_total = window_df["rows_total"].sum()
        base_rows_total = baseline_df["rows_total"].sum()
        base_failure_rate = (
            baseline_df["failure_rows"].sum() / base_rows_total * 100 if base_rows_total else 0.0
        )

        k1, k2, k3, k4 = st.columns(4)
        k1.metric(f"Revenue, Last {n_days}d", f"₹{win_revenue:,.0f}")
        rev_delta = (win_avg_daily - base_avg_daily) / base_avg_daily * 100 if base_avg_daily else None
        k2.metric(
            "Avg Daily Revenue", f"₹{win_avg_daily:,.0f}",
            delta=f"{rev_delta:+.1f}% vs trailing 30d" if rev_delta is not None else None,
        )
        k3.metric(
            "Failure Rate", f"{win_failure_rate:.2f}%",
            delta=f"{win_failure_rate - base_failure_rate:+.2f}pp vs trailing 30d" if base_rows_total else None,
            delta_color="inverse",
        )
        k4.metric("Machines With Sales", f"{window_df.loc[window_df['revenue'] > 0, 'machine_id'].nunique():,}")

        st.divider()

        # ── Per-machine window vs. baseline ─────────────────────────────────
        win_agg = window_df.groupby("machine_id", as_index=False).agg(
            revenue_window=("revenue", "sum"),
            units_window=("sale_qty", "sum"),
            rows_total_window=("rows_total", "sum"),
            failure_rows_window=("failure_rows", "sum"),
            lost_amount_window=("paid_not_dispensed_amount", "sum"),
        )
        base_agg = baseline_df.groupby("machine_id", as_index=False).agg(
            baseline_avg_daily_revenue=("revenue", "mean"),
        )

        attn = machines_f.merge(win_agg, on="machine_id", how="left")
        attn = attn.merge(base_agg, on="machine_id", how="left")
        for _col in ("revenue_window", "units_window", "rows_total_window", "failure_rows_window", "lost_amount_window"):
            attn[_col] = attn[_col].fillna(0)

        attn["avg_daily_window"] = attn["revenue_window"] / n_days
        attn["failure_rate_window_pct"] = (
            attn["failure_rows_window"] / attn["rows_total_window"].replace(0, pd.NA) * 100
        )
        attn["revenue_change_pct"] = (
            (attn["avg_daily_window"] - attn["baseline_avg_daily_revenue"])
            / attn["baseline_avg_daily_revenue"].replace(0, pd.NA) * 100
        )
        attn["no_sales"] = (attn["revenue_window"] == 0) & (attn["baseline_avg_daily_revenue"].fillna(0) > 0)

        # IQR fences on the non-zero-sales subset, so a "No Sales" machine (already
        # its own -100% flag) doesn't skew the fence used for partial declines.
        lower_rev, upper_rev = _iqr_bounds(attn.loc[~attn["no_sales"], "revenue_change_pct"])
        lower_fail, upper_fail = _iqr_bounds(attn.loc[attn["rows_total_window"] > 0, "failure_rate_window_pct"])

        def _attn_flags(row):
            flags = []
            if row["no_sales"]:
                flags.append("🔴 No Sales")
            elif lower_rev is not None and pd.notna(row["revenue_change_pct"]) and row["revenue_change_pct"] < lower_rev:
                flags.append("📉 Revenue Drop")
            if (not row["no_sales"] and upper_fail is not None
                    and pd.notna(row["failure_rate_window_pct"]) and row["failure_rate_window_pct"] > upper_fail):
                flags.append("⚠️ High Failures")
            return flags

        attn["flags"] = attn.apply(_attn_flags, axis=1)
        attn["flag_count"] = attn["flags"].apply(len)
        flagged = attn[attn["flag_count"] > 0].sort_values(
            ["flag_count", "revenue_change_pct"], ascending=[False, True]
        )

        st.subheader("Attention List")
        if flagged.empty:
            st.success(f"No machines flagged in the last {n_days} day(s).")
        else:
            display = flagged.copy()
            display["Flags"] = display["flags"].apply(lambda fl: ", ".join(fl))
            st.dataframe(
                display[[
                    "machine_name", "city", "location", "Flags", "revenue_window",
                    "revenue_change_pct", "failure_rate_window_pct", "lost_amount_window",
                ]].rename(columns={
                    "machine_name": "Machine", "city": "City", "location": "Location",
                    "revenue_window": f"Revenue (Last {n_days}d)", "revenue_change_pct": "vs Baseline %",
                    "failure_rate_window_pct": "Failure Rate %", "lost_amount_window": "Amount Lost",
                }),
                use_container_width=True, hide_index=True,
            )

        st.divider()

        st.subheader("Revenue Change vs Trailing 30-Day Baseline")
        chart_df = attn.dropna(subset=["revenue_change_pct"]).copy()
        if chart_df.empty:
            st.info("Not enough baseline history yet to compare.")
        else:
            chart_df["status"] = chart_df.apply(
                lambda r: "No Sales" if r["no_sales"] else ("Flagged" if r["flag_count"] > 0 else "Normal"),
                axis=1,
            )
            fig_attn = px.bar(
                chart_df.sort_values("revenue_change_pct"), x="revenue_change_pct", y="machine_name",
                orientation="h", color="status",
                color_discrete_map={"No Sales": "#B85C5C", "Flagged": ACCENT, "Normal": PRIMARY},
                title=f"Avg Daily Revenue, Last {n_days}d vs Trailing 30-Day Baseline",
                height=max(420, len(chart_df) * 22),
            )
            fig_attn.update_layout(xaxis_title="Change vs Baseline (%)", yaxis_title="")
            st.plotly_chart(fig_attn, use_container_width=True)

# ---------- REVENUE & SALES ----------
with tab_revenue:
    st.subheader("💰 Revenue & Sales Trends")

    rv_c1, rv_c2 = st.columns(2)
    with rv_c1:
        daily_agg = txn_daily_f.groupby("date", as_index=False)["revenue"].sum()
        fig_d = px.line(daily_agg, x="date", y="revenue", title="Daily Revenue",
                         markers=True, color_discrete_sequence=[PRIMARY])
        fig_d.update_layout(xaxis_title="", yaxis_title="Revenue (₹)")
        st.plotly_chart(fig_d, use_container_width=True)
    with rv_c2:
        daily_units = txn_daily_f.groupby("date", as_index=False)["sale_qty"].sum()
        fig_u = px.bar(daily_units, x="date", y="sale_qty", title="Daily Units Sold",
                        color_discrete_sequence=[ACCENT])
        fig_u.update_layout(xaxis_title="", yaxis_title="Units")
        st.plotly_chart(fig_u, use_container_width=True)

    st.divider()

    if txn_hourly_f.empty:
        st.info("No `Txn_Hourly` data for the current filters.")
    else:
        hourly_avg = txn_hourly_f.groupby("hour", as_index=False)["revenue"].mean()
        fig_h = px.bar(hourly_avg, x="hour", y="revenue", title="Average Revenue by Hour of Day",
                        color_discrete_sequence=[PRIMARY])
        fig_h.update_layout(xaxis_title="Hour", yaxis_title="Avg Revenue (₹)", xaxis=dict(dtick=1))
        st.plotly_chart(fig_h, use_container_width=True)

    st.divider()

    st.subheader("📈 Month-over-Month")
    mom_tab1, mom_tab2 = st.tabs(["Fleet (filtered)", "Drill into one entity"])
    with mom_tab1:
        if txn_daily_f.empty:
            st.info("No data for the current filters.")
        else:
            monthly = (
                txn_daily_f.assign(month=txn_daily_f["date"].values.astype("datetime64[M]"))
                .groupby("month", as_index=False)["revenue"].sum()
                .sort_values("month")
            )
            monthly["mom_change_pct"] = monthly["revenue"].pct_change() * 100
            fig_mom = px.bar(monthly, x="month", y="revenue", title="Monthly Revenue (filtered fleet)",
                              color_discrete_sequence=[PRIMARY])
            fig_mom.update_layout(xaxis_title="", yaxis_title="Revenue (₹)")
            st.plotly_chart(fig_mom, use_container_width=True)
            st.dataframe(
                monthly.rename(columns={"month": "Month", "revenue": "Revenue", "mom_change_pct": "MoM Change %"}),
                use_container_width=True, hide_index=True,
            )
    with mom_tab2:
        rev_mom_df = data["rev_mom"]
        if rev_mom_df.empty:
            st.info("No `Rev_MoM` data loaded.")
        else:
            dr_c1, dr_c2 = st.columns(2)
            with dr_c1:
                dr_level = st.radio("Level", list(LEVEL_LABELS), format_func=lambda k: LEVEL_LABELS[k],
                                     horizontal=True, key="rev_mom_level")
            level_rows = rev_mom_df[rev_mom_df["level"] == dr_level]
            entity_labels = sorted(level_rows["label"].dropna().unique().tolist())
            with dr_c2:
                dr_entity = st.selectbox(LEVEL_LABELS[dr_level], entity_labels, key="rev_mom_entity") if entity_labels else None
            if dr_entity:
                entity_rows = level_rows[level_rows["label"] == dr_entity].sort_values("month_dt")
                fig_e = px.bar(entity_rows, x="month_dt", y="revenue", title=f"Monthly Revenue — {dr_entity}",
                               color_discrete_sequence=[ACCENT])
                fig_e.update_layout(xaxis_title="", yaxis_title="Revenue (₹)")
                st.plotly_chart(fig_e, use_container_width=True)
                st.dataframe(
                    entity_rows[["month", "revenue", "units", "avg_daily_revenue", "mom_change_pct", "partial_month"]]
                    .rename(columns={
                        "month": "Month", "revenue": "Revenue", "units": "Units",
                        "avg_daily_revenue": "Avg Daily Revenue", "mom_change_pct": "MoM Change %",
                        "partial_month": "Partial Month",
                    }),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("No entities available for this level.")

    st.divider()

    st.subheader("🏷️ Top Products")
    if txn_product_f.empty:
        st.info("No `Txn_Product` data for the current filters.")
    else:
        prod_agg = (
            txn_product_f.groupby(["product_name", "brand"], as_index=False)[["sale_qty", "revenue"]]
            .sum().sort_values("revenue", ascending=False)
        )
        fig_p = px.bar(
            prod_agg.head(15).sort_values("revenue"), x="revenue", y="product_name", orientation="h",
            title="Top 15 Products by Revenue", color_discrete_sequence=[PRIMARY],
        )
        fig_p.update_layout(xaxis_title="Revenue (₹)", yaxis_title="")
        st.plotly_chart(fig_p, use_container_width=True)
        st.dataframe(
            prod_agg.rename(columns={"product_name": "Product", "brand": "Brand", "sale_qty": "Units Sold", "revenue": "Revenue"}),
            use_container_width=True, hide_index=True,
        )

# ---------- REFILLING ----------
with tab_refill:
    st.subheader("🔁 Refilling Activity")

    if refill_hourly_f.empty:
        st.info("No `Refill_Hourly` data for the current filters.")
    else:
        rf_c1, rf_c2, rf_c3 = st.columns(3)
        rf_c1.metric("Total Refill Qty", f"{refill_hourly_f['refill_qty'].sum():,.0f}")
        rf_c2.metric("Refill Events (rows)", f"{refill_hourly_f['refill_rows'].sum():,.0f}")
        avg_per_event = (
            refill_hourly_f["refill_qty"].sum() / refill_hourly_f["refill_rows"].sum()
            if refill_hourly_f["refill_rows"].sum() else 0
        )
        rf_c3.metric("Avg Qty / Event", f"{avg_per_event:,.1f}")

        st.divider()

        hourly_refill = refill_hourly_f.groupby("hour", as_index=False)["refill_qty"].sum()
        fig_rf = px.bar(hourly_refill, x="hour", y="refill_qty", title="Refill Quantity by Hour of Day",
                         color_discrete_sequence=[ACCENT])
        fig_rf.update_layout(xaxis_title="Hour", yaxis_title="Qty Refilled", xaxis=dict(dtick=1))
        st.plotly_chart(fig_rf, use_container_width=True)

        st.divider()

        by_machine = (
            refill_hourly_f.groupby(["machine_name", "location"], as_index=False)[["refill_rows", "refill_qty"]]
            .sum().sort_values("refill_qty", ascending=False)
        )
        st.dataframe(
            by_machine.rename(columns={
                "machine_name": "Machine", "location": "Location",
                "refill_rows": "Refill Events", "refill_qty": "Qty Refilled",
            }),
            use_container_width=True, hide_index=True,
        )

    refill_product_df = data["refill_product"]
    if refill_product_df.empty:
        st.info(
            "Product-level refill breakdown isn't available yet — once the "
            "`Refill_Product` tab has rows, this section will show qty refilled per product."
        )

# ---------- FAILURES ----------
with tab_failures:
    st.subheader("🚫 Dispense & Payment Failures")
    st.caption("KPIs below use `Txn_Daily` (respects the exact date range). The detailed breakdown uses `Txn_Failures` (month-level).")

    fl_c1, fl_c2, fl_c3, fl_c4 = st.columns(4)
    fl_c1.metric("Dispense Timeouts", f"{txn_daily_f['dispense_timeout_rows'].sum():,.0f}")
    fl_c2.metric("Paid, Not Dispensed", f"{txn_daily_f['paid_not_dispensed_rows'].sum():,.0f}")
    fl_c3.metric("Amount Lost", f"₹{txn_daily_f['paid_not_dispensed_amount'].sum():,.0f}")
    fl_c4.metric("Payment Failed Rows", f"{txn_daily_f['payment_failed_rows'].sum():,.0f}")

    st.divider()

    lost_by_date = txn_daily_f.groupby("date", as_index=False)["paid_not_dispensed_amount"].sum()
    fig_lost = px.bar(lost_by_date, x="date", y="paid_not_dispensed_amount",
                       title="Amount Lost to Paid-Not-Dispensed, by Day", color_discrete_sequence=[ACCENT])
    fig_lost.update_layout(xaxis_title="", yaxis_title="Amount Lost (₹)")
    st.plotly_chart(fig_lost, use_container_width=True)

    by_machine_loss = (
        txn_daily_f.groupby("machine_name", as_index=False)["paid_not_dispensed_amount"]
        .sum().sort_values("paid_not_dispensed_amount", ascending=False).head(10)
    )
    fig_loss_m = px.bar(
        by_machine_loss.sort_values("paid_not_dispensed_amount"), x="paid_not_dispensed_amount", y="machine_name",
        orientation="h", title="Top 10 Machines by Amount Lost", color_discrete_sequence=[PRIMARY],
    )
    fig_loss_m.update_layout(xaxis_title="Amount Lost (₹)", yaxis_title="")
    st.plotly_chart(fig_loss_m, use_container_width=True)

    st.divider()

    st.subheader("Detailed Breakdown")
    if txn_failures_f.empty:
        st.info("No `Txn_Failures` data for the current filters.")
    else:
        trend = txn_failures_f.groupby("month", as_index=False)[["rows", "amount"]].sum().sort_values("month")
        fig_trend = px.bar(trend, x="month", y="rows", title="Failure Rows by Month", color_discrete_sequence=[ACCENT])
        fig_trend.update_layout(xaxis_title="", yaxis_title="Rows")
        st.plotly_chart(fig_trend, use_container_width=True)

        st.dataframe(
            txn_failures_f.sort_values("month", ascending=False)[[
                "month", "machine_name", "city", "location", "payment_status",
                "dispense_status", "error_code", "rows", "amount",
            ]].rename(columns={
                "month": "Month", "machine_name": "Machine", "city": "City", "location": "Location",
                "payment_status": "Payment Status", "dispense_status": "Dispense Status",
                "error_code": "Error Code", "rows": "Rows", "amount": "Amount",
            }),
            use_container_width=True, hide_index=True,
        )

# ---------- SKU MIX ----------
with tab_sku:
    st.subheader("🧃 SKU Mix & Categories")

    sku_cat_df = data["sku_category_map"]
    if sku_cat_df.empty:
        st.info("No `SKU_Category_Map` data loaded.")
    else:
        cat_agg = sku_cat_df.groupby("category_group", as_index=False)["revenue"].sum().sort_values("revenue", ascending=False)
        sk_c1, sk_c2 = st.columns(2)
        with sk_c1:
            fig_cat_pie = px.pie(cat_agg, names="category_group", values="revenue",
                                  title="Fleet-wide Revenue by Category", color_discrete_sequence=PALETTE)
            st.plotly_chart(fig_cat_pie, use_container_width=True)
        with sk_c2:
            top_products = sku_cat_df.sort_values("revenue", ascending=False).head(15)
            fig_top_prod = px.bar(
                top_products.sort_values("revenue"), x="revenue", y="product_name", orientation="h",
                title="Top 15 Products by Revenue (fleet-wide)", color_discrete_sequence=[PRIMARY],
            )
            fig_top_prod.update_layout(xaxis_title="Revenue (₹)", yaxis_title="")
            st.plotly_chart(fig_top_prod, use_container_width=True)

        st.divider()
        cat_filter = st.multiselect(
            "Filter by category", sorted(sku_cat_df["category_group"].dropna().unique().tolist()),
            key="sku_cat_filter",
        )
        name_search = st.text_input("Search product name", key="sku_name_search")
        table = sku_cat_df.copy()
        if cat_filter:
            table = table[table["category_group"].isin(cat_filter)]
        if name_search:
            table = table[table["product_name"].str.contains(name_search, case=False, na=False)]
        st.dataframe(
            table.sort_values("revenue", ascending=False).rename(columns={
                "product_name": "Product", "brand": "Brand", "api_category": "API Category",
                "category_group": "Category Group", "sold_qty": "Units Sold", "revenue": "Revenue",
                "refilled_qty": "Units Refilled", "current_price": "Current Price (₹)",
            }),
            use_container_width=True, hide_index=True,
        )

    st.divider()

    st.subheader("Breakdown by Machine / Location / Warehouse")
    sku_mix_df = data["sku_mix"]
    if sku_mix_df.empty:
        st.info("No `SKU_Mix` data loaded.")
    else:
        month_label = sku_mix_df["scope_month"].dropna().iloc[0] if sku_mix_df["scope_month"].notna().any() else ""
        scope_options = {"all_time": "All Time", "last_full_month": f"Last Full Month ({month_label})"}

        sm_c1, sm_c2, sm_c3 = st.columns(3)
        with sm_c1:
            sm_scope = st.radio("Scope", list(scope_options), format_func=lambda k: scope_options[k], key="sku_mix_scope")
        with sm_c2:
            sm_level = st.radio("Level", list(LEVEL_LABELS), format_func=lambda k: LEVEL_LABELS[k], key="sku_mix_level")

        scoped = sku_mix_df[(sku_mix_df["scope_kind"] == sm_scope) & (sku_mix_df["level"] == sm_level)]
        entity_labels = sorted(scoped["label"].dropna().unique().tolist())
        with sm_c3:
            sm_entity = st.selectbox(LEVEL_LABELS[sm_level], entity_labels, key="sku_mix_entity") if entity_labels else None

        if sm_entity:
            entity_mix = scoped[scoped["label"] == sm_entity].sort_values("revenue_share_pct", ascending=False)
            fig_mix = px.pie(entity_mix, names="category_group", values="revenue",
                              title=f"Category Revenue Share — {sm_entity}", color_discrete_sequence=PALETTE)
            st.plotly_chart(fig_mix, use_container_width=True)
            st.dataframe(
                entity_mix[["category_group", "sold_qty", "sold_qty_share_pct", "revenue", "revenue_share_pct",
                            "refilled_qty", "refilled_qty_share_pct"]].rename(columns={
                    "category_group": "Category", "sold_qty": "Units Sold", "sold_qty_share_pct": "Units Share %",
                    "revenue": "Revenue", "revenue_share_pct": "Revenue Share %",
                    "refilled_qty": "Units Refilled", "refilled_qty_share_pct": "Refilled Share %",
                }),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("No entities available for this scope/level.")

# ---------- MACHINES ----------
with tab_machines:
    st.subheader("🖥️ Machine Directory")

    if machines_f.empty:
        st.info("No machines match the current filters.")
    else:
        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Machines", f"{len(machines_f):,}")
        mc2.metric("Live", f"{(machines_f['machine_status'] == 'live').sum():,}")
        mc3.metric("Inactive", f"{(machines_f['machine_status'] == 'inactive').sum():,}")
        mc4.metric("Cities", f"{machines_f['city'].nunique():,}")
        mc5.metric("Locations", f"{machines_f['location'].nunique():,}")

        st.divider()

        by_city = machines_f.groupby("city", as_index=False).size().rename(columns={"size": "machines"})
        fig_city = px.bar(by_city.sort_values("machines"), x="machines", y="city", orientation="h",
                           title="Machines by City", color_discrete_sequence=[PRIMARY])
        fig_city.update_layout(xaxis_title="Machines", yaxis_title="")
        st.plotly_chart(fig_city, use_container_width=True)

        st.divider()

        st.subheader("Lifetime Performance Leaderboard")
        metrics_df = data["metrics_summary"]
        machine_metrics = metrics_df[metrics_df["level"] == "machine"].rename(columns={"entity": "machine_id"})
        leaderboard = machines_f.merge(
            machine_metrics[["machine_id", "total_revenue", "total_units", "failure_rate_pct",
                              "avg_last_7d_revenue", "best_day", "best_day_revenue"]],
            on="machine_id", how="left",
        )
        st.dataframe(
            leaderboard[[
                "machine_id", "machine_name", "machine_status", "city", "location", "warehouse",
                "total_revenue", "total_units", "failure_rate_pct", "avg_last_7d_revenue",
                "best_day", "best_day_revenue",
            ]].sort_values("total_revenue", ascending=False).rename(columns={
                "machine_id": "ID", "machine_name": "Machine", "machine_status": "Status",
                "city": "City", "location": "Location", "warehouse": "Warehouse",
                "total_revenue": "Lifetime Revenue", "total_units": "Lifetime Units",
                "failure_rate_pct": "Failure Rate %", "avg_last_7d_revenue": "Avg Last 7d Revenue",
                "best_day": "Best Day", "best_day_revenue": "Best Day Revenue",
            }),
            use_container_width=True, hide_index=True,
        )

# ---------- OUTLIERS ----------
with tab_outliers:
    st.subheader("⚠️ Outlier Machines")
    st.caption(
        "Machines that stand out from the fleet — flagged with the IQR rule "
        "(outside Q1/Q3 ± 1.5×IQR), the same convention boxplots use to mark outliers."
    )

    metrics_df = data["metrics_summary"]
    metrics_machine = metrics_df[metrics_df["level"] == "machine"].rename(columns={"entity": "machine_id"})
    metrics_machine = metrics_machine.merge(
        machines_f[["machine_id", "machine_name", "city", "location"]], on="machine_id", how="inner"
    )
    if not metrics_machine.empty:
        metrics_machine["revenue_momentum_pct"] = (
            (metrics_machine["avg_last_7d_revenue"] - metrics_machine["avg_last_30d_revenue"])
            / metrics_machine["avg_last_30d_revenue"].replace(0, pd.NA) * 100
        )

    st.subheader("By Metric")
    if metrics_machine.empty:
        st.info("No machines with `Metrics_Summary` data for the current filters.")
    else:
        metric_options = {
            "total_revenue": "Total Revenue (₹)",
            "mean_daily_revenue": "Avg Daily Revenue (₹)",
            "failure_rate_pct": "Failure Rate (%)",
            "failed_amount_paid_not_dispensed": "Amount Lost — Paid Not Dispensed (₹)",
            "revenue_momentum_pct": "Revenue Momentum — Last 7d vs Last 30d (%)",
        }
        out_metric = st.selectbox(
            "Metric", list(metric_options), format_func=lambda k: metric_options[k], key="out_metric"
        )
        vals = metrics_machine[["machine_name", "city", "location", out_metric]].dropna(subset=[out_metric])
        lower, upper = _iqr_bounds(vals[out_metric])
        if lower is None:
            st.info("Not enough machines with data for this metric to detect outliers.")
        else:
            vals = vals.copy()
            vals["flag"] = vals[out_metric].apply(lambda v: _flag(v, lower, upper))
            outliers = vals[vals["flag"] != ""].sort_values(out_metric, ascending=False)

            fig_box = px.box(
                vals, y=out_metric, points="all", hover_data=["machine_name", "city"],
                title=f"{metric_options[out_metric]} — Distribution Across Machines",
                color_discrete_sequence=[PRIMARY],
            )
            fig_box.update_layout(yaxis_title=metric_options[out_metric])
            st.plotly_chart(fig_box, use_container_width=True)

            if outliers.empty:
                st.success("No outlier machines detected for this metric.")
            else:
                st.caption(f"Fleet median: {vals[out_metric].median():,.2f} · fence: [{lower:,.2f}, {upper:,.2f}]")
                st.dataframe(
                    outliers.rename(columns={
                        "machine_name": "Machine", "city": "City", "location": "Location",
                        out_metric: metric_options[out_metric], "flag": "Flag",
                    }),
                    use_container_width=True, hide_index=True,
                )

    st.divider()

    st.subheader("📉 Revenue Volatility")
    st.caption(
        "Coefficient of variation (std ÷ mean) of daily revenue per machine, over the date range above — "
        "higher means more erratic day-to-day sales."
    )
    daily_by_machine = (
        txn_daily_f.groupby(["machine_id", "machine_name"])["revenue"]
        .agg(["mean", "std", "count"]).reset_index()
    )
    daily_by_machine = daily_by_machine[daily_by_machine["count"] >= 5]
    if daily_by_machine.empty:
        st.info("Not enough days of data in the current filters to measure volatility.")
    else:
        daily_by_machine["cv_pct"] = (
            daily_by_machine["std"] / daily_by_machine["mean"].replace(0, pd.NA) * 100
        )
        top_volatile = daily_by_machine.dropna(subset=["cv_pct"]).sort_values("cv_pct", ascending=False).head(10)
        fig_cv = px.bar(
            top_volatile.sort_values("cv_pct"), x="cv_pct", y="machine_name", orientation="h",
            title="Most Volatile Machines (Daily Revenue)", color_discrete_sequence=[ACCENT],
        )
        fig_cv.update_layout(xaxis_title="Coefficient of Variation (%)", yaxis_title="")
        st.plotly_chart(fig_cv, use_container_width=True)

    st.divider()

    st.subheader("🧃 Category Mix Outliers")
    st.caption(
        "Machines whose revenue share of a product category is unusually high or low vs. the "
        "fleet (All Time)."
    )
    sku_mix_df = data["sku_mix"]
    mix_machine = sku_mix_df[(sku_mix_df["level"] == "machine") & (sku_mix_df["scope_kind"] == "all_time")]
    mix_machine = mix_machine[mix_machine["label"].isin(machines_f["machine_name"])]
    if mix_machine.empty:
        st.info("No `SKU_Mix` data at machine level for the current filters.")
    else:
        cat_choice = st.selectbox(
            "Category", sorted(mix_machine["category_group"].dropna().unique().tolist()), key="out_cat"
        )
        cat_rows = mix_machine[mix_machine["category_group"] == cat_choice]
        lower_c, upper_c = _iqr_bounds(cat_rows["revenue_share_pct"])
        if lower_c is None:
            st.info("Not enough machines selling this category to detect outliers.")
        else:
            cat_rows = cat_rows.copy()
            cat_rows["flag"] = cat_rows["revenue_share_pct"].apply(lambda v: _flag(v, lower_c, upper_c))
            cat_outliers = cat_rows[cat_rows["flag"] != ""].sort_values("revenue_share_pct", ascending=False)

            fig_cat_box = px.box(
                cat_rows, y="revenue_share_pct", points="all", hover_data=["label"],
                title=f"{cat_choice} — Revenue Share Across Machines", color_discrete_sequence=[PRIMARY],
            )
            fig_cat_box.update_layout(yaxis_title="Revenue Share %")
            st.plotly_chart(fig_cat_box, use_container_width=True)

            if cat_outliers.empty:
                st.success("No outlier machines for this category.")
            else:
                st.caption(f"Fleet median share: {cat_rows['revenue_share_pct'].median():.1f}%")
                st.dataframe(
                    cat_outliers[["label", "revenue_share_pct", "sold_qty", "flag"]].rename(columns={
                        "label": "Machine", "revenue_share_pct": "Revenue Share %",
                        "sold_qty": "Units Sold", "flag": "Flag",
                    }),
                    use_container_width=True, hide_index=True,
                )

with tab_accounts:
    st.subheader("💳 Accounts Ledger")

    if accounts_df.empty:
        st.info(
            "No accounts data loaded. Add `accounts` to `[gids.accounts]` in your Streamlit secrets."
        )
    else:
        # ── Column detection ────────────────────────────────────────────────────
        def _find_ac_col(*keywords):
            for c in accounts_df.columns:
                cl = c.lower().strip()
                if any(k in cl for k in keywords):
                    return c
            return None

        ac_date         = _find_ac_col("date")
        ac_debit        = _find_ac_col("withdrawal", "debit", " dr", "dr.")
        ac_credit       = _find_ac_col("deposit", "credit", " cr", "cr.")
        ac_amount       = _find_ac_col("amount", "amt", "net (") if not (ac_debit and ac_credit) else None
        ac_balance      = _find_ac_col("balance", "bal")
        ac_desc         = _find_ac_col("narration", "description", "particulars", "detail", "remark", "note", "memo")
        ac_cat          = _find_ac_col("category", "account", "head", "ledger", "group")
        ac_bucket       = _find_ac_col("bucket")
        ac_contact      = _find_ac_col("contact n", "vendor", "payee", "party")
        ac_contact_type = _find_ac_col("contact type", "contact_type")
        ac_ready        = _find_ac_col("ready to", "ready?", "import?")

        has_debit_credit = bool(ac_debit and ac_credit)
        has_amount       = bool(ac_amount)

        _AC_CHART_H = 420
        _AC_MONEY_AXIS = dict(tickformat=",.0f", tickprefix="₹")

        # ── Date filter ─────────────────────────────────────────────────────────
        if ac_date and not accounts_df[ac_date].isna().all():
            ac_min = accounts_df[ac_date].dropna().min()
            ac_max = accounts_df[ac_date].dropna().max()
            _ac_dr = st.date_input(
                "Filter by date",
                value=(ac_min.date(), ac_max.date()),
                min_value=ac_min.date(),
                max_value=ac_max.date(),
                key="ac_date_range",
            )
            if isinstance(_ac_dr, tuple) and len(_ac_dr) == 2:
                ac_start, ac_end = _ac_dr
                ac_df = accounts_df[
                    (accounts_df[ac_date].dt.date >= ac_start) &
                    (accounts_df[ac_date].dt.date <= ac_end)
                ].copy()
            else:
                ac_df = accounts_df.copy()
        else:
            ac_df = accounts_df.copy()

        _fc1, _fc2 = st.columns(2)
        if ac_bucket and ac_df[ac_bucket].nunique() > 1:
            _all_buckets = sorted(ac_df[ac_bucket].dropna().unique().tolist())
            _sel_buckets = _fc1.multiselect("Filter by bucket", _all_buckets, default=_all_buckets, key="ac_buckets")
            if _sel_buckets:
                ac_df = ac_df[ac_df[ac_bucket].isin(_sel_buckets)]
        if ac_cat and ac_df[ac_cat].nunique() > 1:
            _all_cats = sorted(ac_df[ac_cat].dropna().unique().tolist())
            _sel_cats = _fc2.multiselect("Filter by category", _all_cats, default=_all_cats, key="ac_cats")
            if _sel_cats:
                ac_df = ac_df[ac_df[ac_cat].isin(_sel_cats)]

        # ── Pre-compute period stats used across multiple sections ──────────────
        if has_debit_credit:
            _ac_dr_s = pd.to_numeric(ac_df[ac_debit],  errors="coerce").fillna(0)
            _ac_cr_s = pd.to_numeric(ac_df[ac_credit], errors="coerce").fillna(0)
            _total_dr = _ac_dr_s.sum()
            _total_cr = _ac_cr_s.sum()
            _net_flow = _total_cr - _total_dr

        _ac_period_days = max(
            (ac_df[ac_date].dropna().max() - ac_df[ac_date].dropna().min()).days, 1
        ) if ac_date and not ac_df[ac_date].isna().all() else 1
        _ac_months = max(_ac_period_days / 30.44, 1)

        # Current balance (last row sorted by date)
        _current_bal = None
        if ac_balance and ac_date:
            _bal_sorted = ac_df.dropna(subset=[ac_date]).sort_values(ac_date)
            _bal_vals = pd.to_numeric(_bal_sorted[ac_balance], errors="coerce").dropna()
            if not _bal_vals.empty:
                _current_bal = _bal_vals.iloc[-1]

        # P&L bucket soft-classification (works even if bucket names change slightly)
        def _bk_is(series, *patterns):
            return series.fillna("").astype(str).str.lower().str.strip().apply(
                lambda b: isinstance(b, str) and any(p in b for p in patterns)
            )

        if ac_bucket:
            _bk_col = ac_df[ac_bucket]
            _rev_m   = _bk_is(_bk_col, "rev")
            _cogs_m  = _bk_is(_bk_col, "cogs", "cost of")
            _opex_m  = _bk_is(_bk_col, "opex", "oper")
            _admin_m = _bk_is(_bk_col, "admin")
            _capex_m = _bk_is(_bk_col, "capex")
            _cap_m   = _bk_is(_bk_col, "cap") & ~_capex_m
            _pers_m  = _bk_is(_bk_col, "pers")
            _intl_m  = _bk_is(_bk_col, "intl", "internal", "transfer")
            _noise_m = _bk_is(_bk_col, "noise")
            _unk_m   = _bk_is(_bk_col, "unk")
        else:
            _rev_m = _cogs_m = _opex_m = _admin_m = _capex_m = _cap_m = \
            _pers_m = _intl_m = _noise_m = _unk_m = pd.Series(False, index=ac_df.index)

        # ── KPI Row ─────────────────────────────────────────────────────────────
        k1, k2, k3, k4, k5 = st.columns(5)
        if has_debit_credit:
            k1.metric("Total Credits",  f"₹{_total_cr:,.0f}")
            k2.metric("Total Debits",   f"₹{_total_dr:,.0f}")
            k3.metric("Net (Cr − Dr)",  f"₹{_net_flow:,.0f}",
                      delta=f"₹{_net_flow:,.0f}", delta_color="normal")
            k4.metric("Transactions",   f"{len(ac_df):,}")
            if _current_bal is not None:
                k5.metric("Current Balance", f"₹{_current_bal:,.0f}")
        elif has_amount:
            _total_amt = pd.to_numeric(ac_df[ac_amount], errors="coerce").fillna(0).sum()
            k1.metric("Total Amount",  f"₹{_total_amt:,.0f}")
            k2.metric("Transactions",  f"{len(ac_df):,}")
            if _current_bal is not None:
                k3.metric("Current Balance", f"₹{_current_bal:,.0f}")
        else:
            k1.metric("Transactions", f"{len(ac_df):,}")

        st.divider()

        # ── P&L Snapshot ────────────────────────────────────────────────────────
        if ac_bucket and has_debit_credit:
            st.subheader("📈 P&L Snapshot")
            st.caption(
                "Operational P&L built from your bucket classification. "
                "Capital flows (CAP/CAPEX), internal transfers (INTL), personal (PERS), "
                "and noise are excluded — they don't hit the P&L."
            )

            _revenue   = _ac_cr_s[_rev_m].sum()
            _cogs      = _ac_dr_s[_cogs_m].sum()
            _gross_p   = _revenue - _cogs
            _gross_m   = _gross_p / _revenue * 100 if _revenue > 0 else 0.0
            _opex_amt  = _ac_dr_s[_opex_m | _admin_m].sum()
            _op_profit = _gross_p - _opex_amt
            _op_margin = _op_profit / _revenue * 100 if _revenue > 0 else 0.0

            pl1, pl2, pl3, pl4, pl5, pl6, pl7 = st.columns(7)
            pl1.metric("Revenue",        f"₹{_revenue:,.0f}")
            pl2.metric("COGS",           f"₹{_cogs:,.0f}")
            pl3.metric("Gross Profit",   f"₹{_gross_p:,.0f}",
                       delta=f"₹{_gross_p:,.0f}", delta_color="normal")
            pl4.metric("Gross Margin",   f"{_gross_m:.1f}%")
            pl5.metric("OPEX + Admin",   f"₹{_opex_amt:,.0f}")
            pl6.metric("Operating Profit", f"₹{_op_profit:,.0f}",
                       delta=f"₹{_op_profit:,.0f}", delta_color="normal")
            pl7.metric("Op. Margin",     f"{_op_margin:.1f}%")

            # Waterfall chart: Revenue → Gross Profit → Operating Profit
            _wf_labels = ["Revenue", "− COGS", "= Gross Profit", "− OPEX/Admin", "= Op. Profit"]
            _wf_values = [_revenue, -_cogs, _gross_p, -_opex_amt, _op_profit]
            _wf_types  = ["absolute", "relative", "total", "relative", "total"]
            _wf_colors = [PRIMARY, "#B85C5C", "#5C9EBF", "#B85C5C",
                          PRIMARY if _op_profit >= 0 else "#B85C5C"]

            import plotly.graph_objects as go
            fig_wf = go.Figure(go.Waterfall(
                name="P&L", orientation="v",
                measure=_wf_types,
                x=_wf_labels,
                y=_wf_values,
                texttemplate="₹%{value:,.0f}",
                textposition="outside",
                connector={"line": {"color": "rgba(0,0,0,0.2)"}},
                decreasing={"marker": {"color": "#B85C5C"}},
                increasing={"marker": {"color": PRIMARY}},
                totals={"marker": {"color": "#5C9EBF"}},
            ))
            fig_wf.update_layout(
                title=dict(text="P&L Waterfall", font=dict(size=16)),
                yaxis=dict(title="Amount", tickformat=",.0f", tickprefix="₹"),
                showlegend=False,
                height=_AC_CHART_H,
                template="plotly_white",
            )
            st.plotly_chart(fig_wf, use_container_width=True)

            # Monthly P&L trend
            if ac_date and not ac_df[ac_date].isna().all():
                _mo_pl = ac_df.copy()
                _mo_pl["_month"] = _mo_pl[ac_date].dt.to_period("M").astype(str)
                _mo_rev  = _mo_pl[_rev_m].groupby(_mo_pl["_month"])[ac_credit].sum()
                _mo_cogs = _mo_pl[_cogs_m].groupby(_mo_pl["_month"])[ac_debit].sum()
                _mo_opex = _mo_pl[_opex_m | _admin_m].groupby(_mo_pl["_month"])[ac_debit].sum()
                _mo_pl_df = pd.DataFrame({
                    "Revenue":          _mo_rev,
                    "COGS":             _mo_cogs,
                    "OPEX+Admin":       _mo_opex,
                }).fillna(0)
                _mo_pl_df["Gross Profit"]    = _mo_pl_df["Revenue"] - _mo_pl_df["COGS"]
                _mo_pl_df["Operating Profit"] = _mo_pl_df["Gross Profit"] - _mo_pl_df["OPEX+Admin"]
                _mo_pl_df = _mo_pl_df.reset_index().rename(columns={"_month": "Month"})

                _mo_lines = _mo_pl_df.melt(
                    id_vars="Month",
                    value_vars=["Revenue", "Gross Profit", "Operating Profit"],
                    var_name="Metric", value_name="Amount",
                )
                fig_mo_pl = px.line(
                    _mo_lines, x="Month", y="Amount", color="Metric", markers=True,
                    title="Monthly P&L Trend",
                    color_discrete_map={
                        "Revenue": PRIMARY,
                        "Gross Profit": "#5C9EBF",
                        "Operating Profit": ACCENT,
                    },
                    template="plotly_white",
                )
                fig_mo_pl.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_mo_pl.update_layout(
                    title=dict(font=dict(size=16)),
                    xaxis_title="",
                    yaxis=dict(title="Amount", **_AC_MONEY_AXIS),
                    legend_title="",
                    height=_AC_CHART_H,
                )
                st.plotly_chart(fig_mo_pl, use_container_width=True)

                # Monthly P&L table with margins
                _mo_pl_display = _mo_pl_df.copy()
                _mo_pl_display["GP %"] = (_mo_pl_df["Gross Profit"] / _mo_pl_df["Revenue"].replace(0, float("nan")) * 100).map("{:.1f}%".format)
                _mo_pl_display["Op %"] = (_mo_pl_df["Operating Profit"] / _mo_pl_df["Revenue"].replace(0, float("nan")) * 100).map("{:.1f}%".format)
                for _col in ["Revenue", "COGS", "OPEX+Admin", "Gross Profit", "Operating Profit"]:
                    _mo_pl_display[_col] = _mo_pl_df[_col].apply(lambda x: f"₹{x:,.0f}")
                _mo_pl_display = _mo_pl_display[["Month", "Revenue", "COGS", "Gross Profit", "GP %", "OPEX+Admin", "Operating Profit", "Op %"]]
                st.dataframe(_mo_pl_display, use_container_width=True, hide_index=True)

            st.divider()

        # ── Cash Flow Analytics ─────────────────────────────────────────────────
        if ac_date and has_debit_credit and not ac_df[ac_date].isna().all():
            st.subheader("💸 Cash Flow Analytics")

            # Daily net cash flow + rolling averages
            _cf_daily = (
                ac_df.groupby(ac_df[ac_date].dt.date)
                .apply(lambda d: pd.to_numeric(d[ac_credit], errors="coerce").fillna(0).sum()
                                 - pd.to_numeric(d[ac_debit], errors="coerce").fillna(0).sum())
                .reset_index()
            )
            _cf_daily.columns = ["date", "net"]
            _cf_daily["date"] = pd.to_datetime(_cf_daily["date"])
            _cf_daily = _cf_daily.sort_values("date").reset_index(drop=True)
            _cf_daily["7d avg"]  = _cf_daily["net"].rolling(7,  min_periods=1).mean()
            _cf_daily["30d avg"] = _cf_daily["net"].rolling(30, min_periods=1).mean()

            _cfa1, _cfa2 = st.columns((3, 2))
            with _cfa1:
                fig_cf = px.bar(
                    _cf_daily, x="date", y="net",
                    title="Daily Net Cash Flow",
                    color_discrete_sequence=["#B0B8C1"],
                    template="plotly_white",
                )
                fig_cf.add_scatter(
                    x=_cf_daily["date"], y=_cf_daily["7d avg"],
                    mode="lines", name="7d avg", line=dict(color=ACCENT, width=2),
                )
                fig_cf.add_scatter(
                    x=_cf_daily["date"], y=_cf_daily["30d avg"],
                    mode="lines", name="30d avg", line=dict(color=PRIMARY, width=2.5),
                )
                fig_cf.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_cf.update_layout(
                    title=dict(font=dict(size=16)),
                    xaxis_title="",
                    yaxis=dict(title="Net Flow", **_AC_MONEY_AXIS),
                    legend_title="",
                    height=_AC_CHART_H,
                )
                st.plotly_chart(fig_cf, use_container_width=True)

            with _cfa2:
                if ac_balance:
                    _bal_df = ac_df.dropna(subset=[ac_date]).copy()
                    _bal_df[ac_balance] = pd.to_numeric(_bal_df[ac_balance], errors="coerce")
                    _bal_df = _bal_df.dropna(subset=[ac_balance]).sort_values(ac_date)
                    if not _bal_df.empty:
                        fig_bal = px.area(
                            _bal_df, x=ac_date, y=ac_balance,
                            title="Running Balance",
                            color_discrete_sequence=[PRIMARY],
                            template="plotly_white",
                        )
                        fig_bal.update_layout(
                            title=dict(font=dict(size=16)),
                            xaxis_title="",
                            yaxis=dict(title="Balance", **_AC_MONEY_AXIS),
                            height=_AC_CHART_H,
                        )
                        st.plotly_chart(fig_bal, use_container_width=True)

            # Burn rate & runway
            if ac_bucket:
                _monthly_rev_avg  = _ac_cr_s[_rev_m].sum()  / _ac_months
                _monthly_cogs_avg = _ac_dr_s[_cogs_m].sum() / _ac_months
                _monthly_opex_avg = _ac_dr_s[_opex_m | _admin_m].sum() / _ac_months
                _monthly_burn     = _monthly_cogs_avg + _monthly_opex_avg

                br1, br2, br3, br4 = st.columns(4)
                br1.metric("Avg Monthly Revenue",  f"₹{_monthly_rev_avg:,.0f}")
                br2.metric("Avg Monthly COGS",     f"₹{_monthly_cogs_avg:,.0f}")
                br3.metric("Avg Monthly OPEX",     f"₹{_monthly_opex_avg:,.0f}")
                br4.metric("Operational Burn Rate", f"₹{_monthly_burn:,.0f} / mo")

                if _current_bal is not None and _monthly_burn > 0:
                    _runway = _current_bal / _monthly_burn
                    st.info(
                        f"At the current operational burn rate of **₹{_monthly_burn:,.0f}/month** "
                        f"(COGS + OPEX + Admin), the current balance of **₹{_current_bal:,.0f}** "
                        f"gives a runway of approximately **{_runway:.1f} months** — "
                        f"assuming revenue drops to zero."
                    )

            st.divider()

        # ── Daily transaction strip ─────────────────────────────────────────────
        if ac_date and has_debit_credit and not ac_df[ac_date].isna().all():
            _daily_dr = ac_df.groupby(ac_df[ac_date].dt.date)[ac_debit].sum().reset_index()
            _daily_cr = ac_df.groupby(ac_df[ac_date].dt.date)[ac_credit].sum().reset_index()
            _daily_dr.columns = ["date", "Debit"]
            _daily_cr.columns = ["date", "Credit"]
            _daily_flow = _daily_dr.merge(_daily_cr, on="date", how="outer").fillna(0)
            _daily_m = _daily_flow.melt(id_vars="date", var_name="Type", value_name="Amount")
            fig_ac_ts = px.bar(
                _daily_m, x="date", y="Amount", color="Type", barmode="stack",
                title="Daily Credits & Debits",
                color_discrete_map={"Debit": "#B85C5C", "Credit": PRIMARY},
                template="plotly_white",
            )
            fig_ac_ts.update_layout(
                title=dict(font=dict(size=16)),
                xaxis_title="",
                yaxis=dict(title="Amount", **_AC_MONEY_AXIS),
                legend_title="",
                height=_AC_CHART_H,
            )
            st.plotly_chart(fig_ac_ts, use_container_width=True)
            st.divider()

        # ── Bucket breakdown ────────────────────────────────────────────────────
        if ac_bucket and has_debit_credit:
            st.subheader("📂 Breakdown by Bucket")
            _bk_cr  = ac_df.groupby(ac_bucket)[ac_credit].sum().reset_index().rename(columns={ac_credit: "Credits"})
            _bk_dr  = ac_df.groupby(ac_bucket)[ac_debit].sum().reset_index().rename(columns={ac_debit: "Debits"})
            _bk_sum = _bk_cr.merge(_bk_dr, on=ac_bucket, how="outer").fillna(0)
            _bk_sum["Net"] = _bk_sum["Credits"] - _bk_sum["Debits"]
            _bk_sum = _bk_sum.sort_values("Net", ascending=False)

            _bb1, _bb2 = st.columns(2)
            with _bb1:
                _bk_m = _bk_sum.melt(id_vars=ac_bucket, value_vars=["Credits", "Debits"], var_name="Type", value_name="Amount")
                fig_bk = px.bar(
                    _bk_m, x=ac_bucket, y="Amount", color="Type", barmode="group",
                    title="Credits & Debits by Bucket",
                    color_discrete_map={"Debits": "#B85C5C", "Credits": PRIMARY},
                    template="plotly_white",
                )
                fig_bk.update_layout(
                    xaxis_title="",
                    yaxis=dict(title="Amount", **_AC_MONEY_AXIS),
                    legend_title="",
                    height=_AC_CHART_H,
                )
                st.plotly_chart(fig_bk, use_container_width=True)
            with _bb2:
                fig_bk_net = px.bar(
                    _bk_sum, x=ac_bucket, y="Net",
                    title="Net Flow by Bucket",
                    color="Net",
                    color_continuous_scale=[[0, "#B85C5C"], [0.5, "#E8E8E8"], [1, PRIMARY]],
                    template="plotly_white",
                )
                fig_bk_net.update_layout(
                    xaxis_title="",
                    yaxis=dict(title="Net", **_AC_MONEY_AXIS),
                    coloraxis_showscale=False,
                    height=_AC_CHART_H,
                )
                fig_bk_net.add_hline(y=0, line_dash="dash", line_color="gray")
                st.plotly_chart(fig_bk_net, use_container_width=True)

            _bk_disp = _bk_sum.copy()
            for _col in ["Credits", "Debits", "Net"]:
                _bk_disp[_col] = _bk_disp[_col].apply(lambda x: f"₹{x:,.0f}")
            st.dataframe(_bk_disp.rename(columns={ac_bucket: "Bucket"}), use_container_width=True, hide_index=True)
            st.divider()

        # ── Category breakdown ──────────────────────────────────────────────────
        if ac_cat:
            st.subheader("🏷️ Breakdown by Category")
            _bc1, _bc2 = st.columns(2)

            if has_debit_credit:
                _cat_dr  = ac_df.groupby(ac_cat)[ac_debit].sum().reset_index().rename(columns={ac_debit: "Debit"})
                _cat_cr  = ac_df.groupby(ac_cat)[ac_credit].sum().reset_index().rename(columns={ac_credit: "Credit"})
                _cat_sum = _cat_dr.merge(_cat_cr, on=ac_cat, how="outer").fillna(0)
                _cat_sum["Net"] = _cat_sum["Credit"] - _cat_sum["Debit"]

                with _bc1:
                    _cat_m = _cat_sum.melt(id_vars=ac_cat, value_vars=["Debit", "Credit"], var_name="Type", value_name="Amount")
                    _n_cats = _cat_sum[ac_cat].nunique()
                    fig_cat = px.bar(
                        _cat_m.sort_values("Amount"),
                        x="Amount", y=ac_cat, color="Type", orientation="h", barmode="group",
                        title="Debits & Credits by Category",
                        color_discrete_map={"Debit": "#B85C5C", "Credit": PRIMARY},
                        template="plotly_white",
                        height=max(_AC_CHART_H, _n_cats * 28 + 120),
                    )
                    fig_cat.update_layout(xaxis=dict(title="Amount", **_AC_MONEY_AXIS), yaxis_title="")
                    st.plotly_chart(fig_cat, use_container_width=True)

                with _bc2:
                    _pie_col = "Credit" if _cat_sum["Credit"].sum() > 0 else "Debit"
                    fig_pie = px.pie(
                        _cat_sum[_cat_sum[_pie_col] > 0], names=ac_cat, values=_pie_col,
                        hole=0.45, title=f"{_pie_col} Share by Category",
                        color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C", "#8CC99E", "#C8A28C"],
                    )
                    fig_pie.update_traces(textinfo="label+percent", textfont_size=12)
                    fig_pie.update_layout(height=_AC_CHART_H, showlegend=False)
                    st.plotly_chart(fig_pie, use_container_width=True)

                _net_display = _cat_sum[[ac_cat, "Credit", "Debit", "Net"]].sort_values("Net", ascending=False).copy()
                for _col in ["Net", "Credit", "Debit"]:
                    _net_display[_col] = _net_display[_col].apply(lambda x: f"₹{x:,.0f}")
                st.dataframe(_net_display.rename(columns={ac_cat: "Category"}), use_container_width=True, hide_index=True)

            elif has_amount:
                _cat_amt = ac_df.groupby(ac_cat)[ac_amount].sum().reset_index().sort_values(ac_amount, ascending=False)
                _cat_amt.columns = ["Category", "Amount"]
                with _bc1:
                    fig_cat = px.bar(
                        _cat_amt.sort_values("Amount"), x="Amount", y="Category", orientation="h",
                        title="Amount by Category", color_discrete_sequence=[PRIMARY],
                        template="plotly_white",
                    )
                    fig_cat.update_layout(xaxis=dict(title="Amount", **_AC_MONEY_AXIS), yaxis_title="", height=_AC_CHART_H)
                    st.plotly_chart(fig_cat, use_container_width=True)
                with _bc2:
                    fig_pie = px.pie(
                        _cat_amt[_cat_amt["Amount"] > 0], names="Category", values="Amount",
                        hole=0.45, title="Amount Share by Category",
                        color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C", "#8CC99E", "#C8A28C"],
                    )
                    fig_pie.update_traces(textinfo="label+percent", textfont_size=12)
                    fig_pie.update_layout(height=_AC_CHART_H, showlegend=False)
                    st.plotly_chart(fig_pie, use_container_width=True)
            st.divider()

        # ── Vendor / Contact Analysis ───────────────────────────────────────────
        if ac_contact and has_debit_credit:
            st.subheader("👥 Vendor & Contact Analysis")
            _vc1, _vc2 = st.columns(2)

            with _vc1:
                _top_spend = (
                    ac_df.groupby(ac_contact)[ac_debit].sum()
                    .sort_values(ascending=False).head(15).reset_index()
                )
                _top_spend.columns = ["Contact", "Total Spent"]
                _top_spend = _top_spend[_top_spend["Total Spent"] > 0]
                fig_vs = px.bar(
                    _top_spend.sort_values("Total Spent"),
                    x="Total Spent", y="Contact", orientation="h",
                    title="Top 15 by Total Spend (Debits)",
                    color_discrete_sequence=["#B85C5C"],
                    template="plotly_white",
                )
                fig_vs.update_layout(
                    xaxis=dict(title="Amount", **_AC_MONEY_AXIS),
                    yaxis_title="",
                    height=max(_AC_CHART_H, len(_top_spend) * 26 + 120),
                )
                st.plotly_chart(fig_vs, use_container_width=True)

            with _vc2:
                _top_recv = (
                    ac_df.groupby(ac_contact)[ac_credit].sum()
                    .sort_values(ascending=False).head(15).reset_index()
                )
                _top_recv.columns = ["Contact", "Total Received"]
                _top_recv = _top_recv[_top_recv["Total Received"] > 0]
                fig_vr = px.bar(
                    _top_recv.sort_values("Total Received"),
                    x="Total Received", y="Contact", orientation="h",
                    title="Top 15 by Credits Received",
                    color_discrete_sequence=[PRIMARY],
                    template="plotly_white",
                )
                fig_vr.update_layout(
                    xaxis=dict(title="Amount", **_AC_MONEY_AXIS),
                    yaxis_title="",
                    height=max(_AC_CHART_H, len(_top_recv) * 26 + 120),
                )
                st.plotly_chart(fig_vr, use_container_width=True)

            if ac_contact_type:
                _ct_dr = ac_df.groupby(ac_contact_type)[ac_debit].sum().reset_index().rename(columns={ac_debit: "Debits"})
                _ct_cr = ac_df.groupby(ac_contact_type)[ac_credit].sum().reset_index().rename(columns={ac_credit: "Credits"})
                _ct_sum = _ct_dr.merge(_ct_cr, on=ac_contact_type, how="outer").fillna(0)
                _ct_m = _ct_sum.melt(id_vars=ac_contact_type, value_vars=["Debits", "Credits"], var_name="Type", value_name="Amount")
                fig_ct = px.bar(
                    _ct_m, x=ac_contact_type, y="Amount", color="Type", barmode="group",
                    title="Cash Flows by Contact Type",
                    color_discrete_map={"Debits": "#B85C5C", "Credits": PRIMARY},
                    template="plotly_white",
                )
                fig_ct.update_layout(
                    xaxis_title="",
                    yaxis=dict(title="Amount", **_AC_MONEY_AXIS),
                    legend_title="",
                    height=_AC_CHART_H,
                )
                st.plotly_chart(fig_ct, use_container_width=True)

            st.divider()

        # ── Alerts & Attention Items ────────────────────────────────────────────
        _alerts = []
        if ac_bucket:
            _unk_df  = ac_df[_unk_m].copy()
            _pers_df = ac_df[_pers_m].copy()
            if not _unk_df.empty:
                _alerts.append(("🔴 Unclassified (UNK) transactions", _unk_df,
                                f"{len(_unk_df)} transactions worth "
                                f"₹{pd.to_numeric(_unk_df[ac_debit], errors='coerce').fillna(0).sum():,.0f} in debits — "
                                "categorise before GST filing."))
            if not _pers_df.empty:
                _pers_total = pd.to_numeric(_pers_df[ac_debit], errors="coerce").fillna(0).sum()
                _alerts.append(("🟠 Personal (PERS) transactions", _pers_df,
                                f"{len(_pers_df)} personal transactions totalling ₹{_pers_total:,.0f} in debits — "
                                "ensure these are recorded as drawings / partner withdrawals, not business expenses."))

        if ac_ready:
            _not_ready = ac_df[ac_df[ac_ready].astype(str).str.strip().str.lower().ne("yes")].copy()
            if not _not_ready.empty:
                _alerts.append(("🟡 Not yet ready to import", _not_ready,
                                f"{len(_not_ready)} transactions not marked 'Yes' in 'Ready to Import?' — review before Zoho import."))

        if has_debit_credit:
            _dr_nonzero = _ac_dr_s[_ac_dr_s > 0]
            if len(_dr_nonzero) >= 4:
                _outlier_thresh = _dr_nonzero.mean() + 2.5 * _dr_nonzero.std()
                _large_df = ac_df[_ac_dr_s > _outlier_thresh].copy()
                if not _large_df.empty:
                    _alerts.append(("🔵 Large debit outliers (> 2.5σ)", _large_df,
                                    f"{len(_large_df)} unusually large debits (above ₹{_outlier_thresh:,.0f}) — verify each is intentional."))

        if _alerts:
            st.subheader("⚠️ Alerts & Attention Items")
            for _alert_title, _alert_df, _alert_msg in _alerts:
                with st.expander(f"{_alert_title} ({len(_alert_df)})", expanded=True):
                    st.caption(_alert_msg)
                    _disp_alert = _alert_df.copy()
                    if ac_date and ac_date in _disp_alert.columns:
                        try:
                            _disp_alert[ac_date] = _disp_alert[ac_date].dt.strftime("%d %b %Y")
                        except Exception:
                            pass
                    st.dataframe(_disp_alert, use_container_width=True, hide_index=True)
            st.divider()

        # ── Monthly Breakdown ────────────────────────────────────────────────────
        if ac_date and not ac_df[ac_date].isna().all():
            st.subheader("📅 Monthly Breakdown")
            _mo_df = ac_df.copy()
            _mo_df["_month"] = _mo_df[ac_date].dt.to_period("M").astype(str)

            if has_debit_credit:
                _mo_sum = (
                    _mo_df.groupby("_month")[[ac_debit, ac_credit]]
                    .sum().reset_index()
                    .rename(columns={"_month": "Month", ac_debit: "Debits", ac_credit: "Credits"})
                )
                _mo_sum["Net"]  = _mo_sum["Credits"] - _mo_sum["Debits"]
                _mo_sum["Txns"] = _mo_df.groupby("_month").size().values

                _mo_bar_m = _mo_sum.melt(id_vars="Month", value_vars=["Debits", "Credits"], var_name="Type", value_name="Amount")
                fig_mo = px.bar(
                    _mo_bar_m, x="Month", y="Amount", color="Type", barmode="group",
                    title="Monthly Cash In vs Out",
                    color_discrete_map={"Debits": "#B85C5C", "Credits": PRIMARY},
                    template="plotly_white",
                )
                fig_mo.update_layout(
                    title=dict(font=dict(size=16)),
                    xaxis_title="",
                    yaxis=dict(title="Amount", **_AC_MONEY_AXIS),
                    legend_title="",
                    height=_AC_CHART_H,
                )
                st.plotly_chart(fig_mo, use_container_width=True)

                fig_mo_net = px.line(
                    _mo_sum, x="Month", y="Net", markers=True,
                    title="Monthly Net Flow",
                    color_discrete_sequence=[PRIMARY],
                    template="plotly_white",
                )
                fig_mo_net.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_mo_net.update_layout(
                    xaxis_title="", yaxis=dict(title="Net", **_AC_MONEY_AXIS), height=300,
                )
                st.plotly_chart(fig_mo_net, use_container_width=True)

                if ac_bucket:
                    _mo_rev_s  = _mo_df[_rev_m].groupby(_mo_df["_month"])[ac_credit].sum()
                    _mo_cogs_s = _mo_df[_cogs_m].groupby(_mo_df["_month"])[ac_debit].sum()
                    _mo_opex_s = _mo_df[_opex_m | _admin_m].groupby(_mo_df["_month"])[ac_debit].sum()
                    _mo_full   = _mo_sum.copy().set_index("Month")
                    _mo_full["Revenue"]      = _mo_rev_s.reindex(_mo_full.index).fillna(0)
                    _mo_full["COGS"]         = _mo_cogs_s.reindex(_mo_full.index).fillna(0)
                    _mo_full["Gross Profit"] = _mo_full["Revenue"] - _mo_full["COGS"]
                    _mo_full["OPEX"]         = _mo_opex_s.reindex(_mo_full.index).fillna(0)
                    _mo_full["Op Profit"]    = _mo_full["Gross Profit"] - _mo_full["OPEX"]
                    _mo_full = _mo_full.reset_index()
                    _mo_tbl  = _mo_full.copy()
                    _mo_tbl["GP %"] = (_mo_full["Gross Profit"] / _mo_full["Revenue"].replace(0, float("nan")) * 100).map("{:.1f}%".format)
                    _mo_tbl["Op %"] = (_mo_full["Op Profit"] / _mo_full["Revenue"].replace(0, float("nan")) * 100).map("{:.1f}%".format)
                    for _c in ["Revenue", "COGS", "Gross Profit", "OPEX", "Op Profit", "Credits", "Debits", "Net"]:
                        _mo_tbl[_c] = _mo_full[_c].apply(lambda x: f"₹{x:,.0f}")
                    _mo_tbl = _mo_tbl[["Month", "Revenue", "COGS", "Gross Profit", "GP %", "OPEX", "Op Profit", "Op %", "Credits", "Debits", "Net", "Txns"]]
                else:
                    _mo_tbl = _mo_sum.copy()
                    for _c in ["Credits", "Debits", "Net"]:
                        _mo_tbl[_c] = _mo_sum[_c].apply(lambda x: f"₹{x:,.0f}")
                st.dataframe(_mo_tbl, use_container_width=True, hide_index=True)

            elif has_amount:
                _mo_sum2 = _mo_df.groupby("_month")[ac_amount].sum().reset_index()
                _mo_sum2.columns = ["Month", "Amount"]
                fig_mo = px.bar(_mo_sum2, x="Month", y="Amount", title="Monthly Total Amounts",
                                color_discrete_sequence=[PRIMARY], template="plotly_white")
                fig_mo.update_layout(xaxis_title="", yaxis=dict(title="Amount", **_AC_MONEY_AXIS), height=_AC_CHART_H)
                st.plotly_chart(fig_mo, use_container_width=True)

            st.divider()

        # ── Latest Day Breakdown ─────────────────────────────────────────────────
        if ac_date and has_debit_credit and not ac_df[ac_date].isna().all():
            _latest_date = ac_df[ac_date].dropna().dt.date.max()
            _latest_df   = ac_df[ac_df[ac_date].dt.date == _latest_date].copy()

            if not _latest_df.empty:
                _ld_label = _latest_date.strftime("%d %b %Y")
                st.subheader(f"📆 Latest Day — {_ld_label}")

                _ld_cr  = pd.to_numeric(_latest_df[ac_credit], errors="coerce").fillna(0).sum()
                _ld_dr  = pd.to_numeric(_latest_df[ac_debit],  errors="coerce").fillna(0).sum()
                _ld_net = _ld_cr - _ld_dr

                ld1, ld2, ld3, ld4 = st.columns(4)
                ld1.metric("Credits",      f"₹{_ld_cr:,.0f}")
                ld2.metric("Debits",       f"₹{_ld_dr:,.0f}")
                ld3.metric("Net",          f"₹{_ld_net:,.0f}", delta=f"₹{_ld_net:,.0f}", delta_color="normal")
                ld4.metric("Transactions", f"{len(_latest_df):,}")

                if ac_bucket:
                    _ld_bk_cr = _latest_df.groupby(ac_bucket)[ac_credit].sum().reset_index().rename(columns={ac_credit: "Credits"})
                    _ld_bk_dr = _latest_df.groupby(ac_bucket)[ac_debit].sum().reset_index().rename(columns={ac_debit: "Debits"})
                    _ld_bk    = _ld_bk_cr.merge(_ld_bk_dr, on=ac_bucket, how="outer").fillna(0)
                    _ld_bk["Net"] = _ld_bk["Credits"] - _ld_bk["Debits"]
                    _ld_bk_m  = _ld_bk.melt(id_vars=ac_bucket, value_vars=["Credits", "Debits"], var_name="Type", value_name="Amount")
                    fig_ld_bk = px.bar(
                        _ld_bk_m, x=ac_bucket, y="Amount", color="Type", barmode="group",
                        title=f"Bucket Breakdown — {_ld_label}",
                        color_discrete_map={"Debits": "#B85C5C", "Credits": PRIMARY},
                        template="plotly_white",
                    )
                    fig_ld_bk.update_layout(
                        xaxis_title="", yaxis=dict(title="Amount", **_AC_MONEY_AXIS),
                        legend_title="", height=340,
                    )
                    st.plotly_chart(fig_ld_bk, use_container_width=True)

                _ld_show = _latest_df.copy()
                if ac_date in _ld_show.columns:
                    try:
                        _ld_show[ac_date] = _ld_show[ac_date].dt.strftime("%d %b %Y")
                    except Exception:
                        pass
                st.dataframe(_ld_show, use_container_width=True, hide_index=True)
                st.divider()

        # ── Full Ledger ─────────────────────────────────────────────────────────
        st.subheader("📋 Full Ledger")
        _disp = ac_df.copy()
        if ac_date and ac_date in _disp.columns:
            try:
                _disp[ac_date] = _disp[ac_date].dt.strftime("%d %b %Y")
            except Exception:
                pass
        _sort_col = ac_date if ac_date and ac_date in _disp.columns else None
        st.dataframe(
            _disp.sort_values(_sort_col, ascending=False) if _sort_col else _disp,
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("ℹ️ Auto-detected column mapping", expanded=False):
            st.caption(
                f"Date: `{ac_date or '—'}` | "
                f"Debit: `{ac_debit or '—'}` | "
                f"Credit: `{ac_credit or '—'}` | "
                f"Balance: `{ac_balance or '—'}` | "
                f"Bucket: `{ac_bucket or '—'}` | "
                f"Category: `{ac_cat or '—'}` | "
                f"Contact: `{ac_contact or '—'}` | "
                f"Description: `{ac_desc or '—'}`\n\n"
                "Rename column headers in your Google Sheet to include the keywords "
                "`date`, `withdrawal`/`debit`, `deposit`/`credit`, `balance`, `bucket`, "
                "`category`, `contact n`, `narration` if detection is off."
            )

# ============================================================
# 9. HR TAB — employee payments, sourced from the Accounts ledger
# ============================================================
with tab_hr:
    st.subheader("👥 HR — Employee Payments")

    if accounts_df.empty:
        st.info(
            "No accounts data loaded. Add `accounts` to `[gids.accounts]` in your Streamlit secrets."
        )
    else:
        def _find_hr_col(*keywords):
            for c in accounts_df.columns:
                cl = c.lower().strip()
                if any(k in cl for k in keywords):
                    return c
            return None

        hr_date         = _find_hr_col("date")
        hr_debit        = _find_hr_col("withdrawal", "debit", " dr", "dr.")
        hr_credit       = _find_hr_col("deposit", "credit", " cr", "cr.")
        hr_amount       = _find_hr_col("amount", "amt", "net (") if not (hr_debit and hr_credit) else None
        hr_desc         = _find_hr_col("narration", "description", "particulars", "detail", "remark", "note", "memo")
        hr_cat          = _find_hr_col("category", "account", "head", "ledger", "group")
        hr_bucket       = _find_hr_col("bucket")
        hr_contact      = _find_hr_col("contact n", "vendor", "payee", "party")
        hr_contact_type = _find_hr_col("contact type", "contact_type")

        has_debit_credit = bool(hr_debit and hr_credit)
        has_amount       = bool(hr_amount)

        if not hr_contact or not (has_debit_credit or has_amount):
            st.info(
                "Couldn't find a contact/payee column and an amount column in the Accounts sheet — "
                "HR analysis needs both to identify who was paid and how much."
            )
        else:
            _HR_CHART_H = 420
            _HR_MONEY_AXIS = dict(tickformat=",.0f", tickprefix="₹")

            # ── Identify employee/payroll rows by keyword match on category, bucket,
            # contact type or narration — same soft-classification approach as the
            # Accounts tab's bucket detection.
            _HR_KEYWORDS = ["employee", "staff", "salary", "salaries", "wage", "payroll", "hr "]

            def _hr_is(series):
                return series.fillna("").astype(str).str.lower().str.strip().apply(
                    lambda v: isinstance(v, str) and any(k in v for k in _HR_KEYWORDS)
                )

            _hr_mask = pd.Series(False, index=accounts_df.index)
            if hr_contact_type:
                _hr_mask |= _hr_is(accounts_df[hr_contact_type])
            if hr_cat:
                _hr_mask |= _hr_is(accounts_df[hr_cat])
            if hr_bucket:
                _hr_mask |= _hr_is(accounts_df[hr_bucket])
            if hr_desc:
                _hr_mask |= _hr_is(accounts_df[hr_desc])

            hr_df = accounts_df[_hr_mask].copy()

            if hr_df.empty:
                st.info(
                    "No employee/payroll transactions detected. Tag employee payments in your Accounts "
                    "sheet with a Category, Bucket, Contact Type or Narration containing "
                    "'Salary', 'Wages', 'Staff', 'Employee' or 'Payroll' for them to show up here."
                )
            else:
                # ── Date filter ────────────────────────────────────────────────
                if hr_date and not hr_df[hr_date].isna().all():
                    hr_min = hr_df[hr_date].dropna().min()
                    hr_max = hr_df[hr_date].dropna().max()
                    _hr_dr = st.date_input(
                        "Filter by date",
                        value=(hr_min.date(), hr_max.date()),
                        min_value=hr_min.date(),
                        max_value=hr_max.date(),
                        key="hr_date_range",
                    )
                    if isinstance(_hr_dr, tuple) and len(_hr_dr) == 2:
                        hr_start, hr_end = _hr_dr
                        hr_df = hr_df[
                            (hr_df[hr_date].dt.date >= hr_start) &
                            (hr_df[hr_date].dt.date <= hr_end)
                        ]

                _all_emp = sorted(hr_df[hr_contact].dropna().unique().tolist())
                _sel_emp = st.multiselect("Filter by employee", _all_emp, default=_all_emp, key="hr_employees")
                if _sel_emp:
                    hr_df = hr_df[hr_df[hr_contact].isin(_sel_emp)]

                # ── Amount paid per row (money going out to the employee) ───────
                if has_debit_credit:
                    hr_df["_paid"] = pd.to_numeric(hr_df[hr_debit], errors="coerce").fillna(0)
                else:
                    hr_df["_paid"] = pd.to_numeric(hr_df[hr_amount], errors="coerce").fillna(0)

                # ── KPI Row ────────────────────────────────────────────────────
                _total_paid  = hr_df["_paid"].sum()
                _n_employees = hr_df[hr_contact].nunique()
                _n_payments  = len(hr_df)
                _avg_payment = hr_df["_paid"].mean() if _n_payments else 0

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total Paid Out", f"₹{_total_paid:,.0f}")
                k2.metric("Employees",      f"{_n_employees:,}")
                k3.metric("Payments",       f"{_n_payments:,}")
                k4.metric("Avg. Payment",   f"₹{_avg_payment:,.0f}")

                if hr_date and not hr_df[hr_date].isna().all():
                    _this_month = pd.Timestamp.now().to_period("M")
                    _mtd = hr_df[hr_df[hr_date].dt.to_period("M") == _this_month]["_paid"].sum()
                    st.caption(f"Paid so far this month ({_this_month}): ₹{_mtd:,.0f}")

                st.divider()

                # ── Per-employee summary ──────────────────────────────────────
                st.subheader("🧾 Per-Employee Summary")
                _emp_summary = hr_df.groupby(hr_contact).agg(
                    **{
                        "Total Paid":  ("_paid", "sum"),
                        "Payments":    ("_paid", "count"),
                        "Avg Payment": ("_paid", "mean"),
                    }
                )
                if hr_date:
                    _emp_summary["Last Paid"]  = hr_df.groupby(hr_contact)[hr_date].max()
                    _emp_summary["First Paid"] = hr_df.groupby(hr_contact)[hr_date].min()
                _emp_summary = _emp_summary.reset_index().rename(columns={hr_contact: "Employee"})
                _emp_summary = _emp_summary.sort_values("Total Paid", ascending=False)

                _es1, _es2 = st.columns(2)
                with _es1:
                    fig_emp = px.bar(
                        _emp_summary.sort_values("Total Paid"),
                        x="Total Paid", y="Employee", orientation="h",
                        title="Total Paid by Employee",
                        color_discrete_sequence=[PRIMARY],
                        template="plotly_white",
                        height=max(_HR_CHART_H, len(_emp_summary) * 28 + 120),
                    )
                    fig_emp.update_layout(xaxis=dict(title="Amount", **_HR_MONEY_AXIS), yaxis_title="")
                    st.plotly_chart(fig_emp, use_container_width=True)

                with _es2:
                    _pie_df = _emp_summary[_emp_summary["Total Paid"] > 0]
                    fig_pie = px.pie(
                        _pie_df, names="Employee", values="Total Paid",
                        hole=0.45, title="Payroll Share by Employee",
                        color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C", "#8CC99E", "#C8A28C"],
                    )
                    fig_pie.update_traces(textinfo="label+percent", textfont_size=12)
                    fig_pie.update_layout(height=_HR_CHART_H, showlegend=False)
                    st.plotly_chart(fig_pie, use_container_width=True)

                _emp_disp = _emp_summary.copy()
                for _col in ["Total Paid", "Avg Payment"]:
                    _emp_disp[_col] = _emp_disp[_col].apply(lambda x: f"₹{x:,.0f}")
                for _col in ["Last Paid", "First Paid"]:
                    if _col in _emp_disp.columns:
                        _emp_disp[_col] = _emp_disp[_col].dt.strftime("%d %b %Y")
                st.dataframe(_emp_disp, use_container_width=True, hide_index=True)
                st.divider()

                # ── Monthly payroll trend ───────────────────────────────────────
                if hr_date and not hr_df[hr_date].isna().all():
                    st.subheader("📅 Monthly Payroll Trend")
                    _mo_hr = hr_df.copy()
                    _mo_hr["_month"] = _mo_hr[hr_date].dt.to_period("M").astype(str)
                    _mo_hr_sum = _mo_hr.groupby(["_month", hr_contact])["_paid"].sum().reset_index()
                    _mo_hr_sum.columns = ["Month", "Employee", "Amount"]
                    fig_mo_hr = px.bar(
                        _mo_hr_sum, x="Month", y="Amount", color="Employee", barmode="stack",
                        title="Monthly Payroll by Employee",
                        template="plotly_white",
                    )
                    fig_mo_hr.update_layout(
                        xaxis_title="",
                        yaxis=dict(title="Amount", **_HR_MONEY_AXIS),
                        legend_title="",
                        height=_HR_CHART_H,
                    )
                    st.plotly_chart(fig_mo_hr, use_container_width=True)
                    st.divider()

                # ── Full payment history ────────────────────────────────────────
                st.subheader("📋 Full Payment History")
                _hr_cols = []
                if hr_date:
                    _hr_cols.append(hr_date)
                _hr_cols.append(hr_contact)
                _hr_cols.append("_paid")
                if hr_cat:
                    _hr_cols.append(hr_cat)
                if hr_bucket:
                    _hr_cols.append(hr_bucket)
                if hr_desc:
                    _hr_cols.append(hr_desc)

                _hr_hist = hr_df[_hr_cols].copy().rename(columns={hr_contact: "Employee", "_paid": "Amount Paid"})
                if hr_date:
                    _hr_hist = _hr_hist.rename(columns={hr_date: "Date"}).sort_values("Date", ascending=False)
                    _hr_hist["Date"] = _hr_hist["Date"].dt.strftime("%d %b %Y")
                if hr_cat:
                    _hr_hist = _hr_hist.rename(columns={hr_cat: "Category"})
                if hr_bucket:
                    _hr_hist = _hr_hist.rename(columns={hr_bucket: "Bucket"})
                if hr_desc:
                    _hr_hist = _hr_hist.rename(columns={hr_desc: "Note"})
                _hr_hist["Amount Paid"] = _hr_hist["Amount Paid"].apply(lambda x: f"₹{x:,.0f}")
                st.dataframe(_hr_hist, use_container_width=True, hide_index=True)

                with st.expander("ℹ️ How employees are detected", expanded=False):
                    st.caption(
                        "A transaction is treated as an employee/payroll payment if its Category, Bucket, "
                        "Contact Type, or Narration contains any of: "
                        f"{', '.join(sorted(set(k.strip() for k in _HR_KEYWORDS)))}. "
                        "Tag your Accounts sheet accordingly (e.g. Category = 'Salary', Contact Type = 'Employee') "
                        "for accurate payroll tracking — the payee/contact name is used as the employee name."
                    )

