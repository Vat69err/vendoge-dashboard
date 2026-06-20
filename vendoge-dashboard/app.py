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

import urllib.parse
from datetime import datetime, timedelta

import numpy as np
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

    return sales, refill, stockout


try:
    sales_df, refill_df, stockout_df = load_data()
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

all_machines = sorted(sales_df["machine"].dropna().unique().tolist())
machine_sel = st.sidebar.multiselect("Machines", all_machines, default=all_machines)

if st.sidebar.button("🔄 Refresh data now"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(f"Last pulled: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
st.sidebar.caption("Data auto-refreshes every 5 minutes.")


def in_range(df, col="date"):
    mask = (df[col].dt.date >= start_date) & (df[col].dt.date <= end_date)
    return df.loc[mask].copy()


sales_f = in_range(sales_df)
sales_f = sales_f[sales_f["machine"].isin(machine_sel)] if machine_sel else sales_f
refill_f = in_range(refill_df)
stockout_f = in_range(stockout_df)
stockout_f = stockout_f[stockout_f["machine"].isin(machine_sel)] if machine_sel else stockout_f

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
# 5. TABS
# ============================================================
tab_overview, tab_sales, tab_refill, tab_stockout, tab_predict, tab_ops = st.tabs(
    ["📊 Overview", "🛒 Machine Sales", "🔁 Refilling", "🚫 Stock-Outs", "🔮 Predictions", "⚙️ Operations"]
)

# ---------- OVERVIEW ----------
with tab_overview:
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

# ---------- MACHINE SALES ----------
with tab_sales:
    c1, c2 = st.columns(2)
    with c1:
        brand_sel = st.multiselect(
            "Brand", sorted(sales_f["brand_name"].dropna().unique().tolist())
        )
    with c2:
        cat_sel = st.multiselect(
            "Category", sorted(sales_f["category"].dropna().unique().tolist())
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
        refillers = sorted(refill_f["refiller_name"].dropna().unique().tolist())
        refiller_sel = st.multiselect("Refiller", refillers, default=refillers)
    with c2:
        st.metric("Total Refill Value", f"₹{refill_f['amount'].sum():,.0f}")

    rf = refill_f[refill_f["refiller_name"].isin(refiller_sel)] if refiller_sel else refill_f

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

    st.subheader("Refill log")
    st.dataframe(rf.sort_values("date", ascending=False), use_container_width=True)

# ---------- STOCK-OUTS ----------
with tab_stockout:
    if stockout_f.empty:
        st.info("No stock-out events in this date range. 🎉")
    else:
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

    # ---- Shared calculations (use full, unfiltered history for accuracy) ----
    today = sales_df["date"].max()

    sales_by_product_day = (
        sales_df.groupby(["product_id", "product_name", sales_df["date"]])["total_qty"]
        .sum().reset_index()
    )

    latest_refill = (
        refill_df.sort_values("date")
        .groupby("product_id")
        .tail(1)[["product_id", "product_name", "brand_name", "date", "qty_after_refill"]]
        .rename(columns={"date": "last_refill_date"})
    )

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
                prod_sales["date"] > today - pd.Timedelta(days=rate_window_days)
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

    st.subheader("📈 Sales Forecast")
    forecast_col1, forecast_col2 = st.columns(2)
    with forecast_col1:
        forecast_machine = st.selectbox(
            "Machine", ["All machines"] + sorted(sales_df["machine"].dropna().unique().tolist())
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

    # ---- 7a. Top-selling products per machine ----
    st.subheader("🏆 Top-Selling Products per Machine")
    top_n_sel = st.slider("Show top N products per machine", 3, 15, 5, key="ops_topn")

    if "machine" in sales_df.columns and "product_name" in sales_df.columns:
        top_per_machine = (
            sales_df.groupby(["machine", "product_name"])["total_sales"]
            .sum()
            .reset_index()
            .sort_values(["machine", "total_sales"], ascending=[True, False])
        )
        top_per_machine = (
            top_per_machine.groupby("machine")
            .head(top_n_sel)
            .reset_index(drop=True)
        )
        machines_list = sorted(top_per_machine["machine"].unique())
        cols = st.columns(min(len(machines_list), 3))
        for i, machine in enumerate(machines_list):
            col = cols[i % len(cols)]
            with col:
                mdf = top_per_machine[top_per_machine["machine"] == machine].copy()
                fig_top = px.bar(
                    mdf.sort_values("total_sales"),
                    x="total_sales", y="product_name", orientation="h",
                    title=f"{machine}",
                    color_discrete_sequence=[PRIMARY],
                )
                fig_top.update_layout(
                    xaxis_title="Sales (₹)", yaxis_title="",
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=300,
                )
                st.plotly_chart(fig_top, use_container_width=True)
    else:
        st.info("Machine or product data not available.")

    st.divider()

    # ---- 7b. Ideal refill day ----
    st.subheader("📅 Ideal Refill Day")
    st.caption(
        "Based on which days of the week your machines sell the most — "
        "refill **before** these peaks to avoid stock-outs."
    )

    if not sales_df.empty:
        sales_df["dow"] = sales_df["date"].dt.dayofweek
        dow_labels = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        sales_df["dow_label"] = sales_df["dow"].map(dow_labels)

        # Sales by day of week per machine
        dow_by_machine = (
            sales_df.groupby(["machine", "dow", "dow_label"])["total_qty"]
            .mean()
            .reset_index()
            .sort_values("dow")
        )

        # Stockout by day of week
        if not stockout_df.empty:
            stockout_df["dow"] = stockout_df["date"].dt.dayofweek
            stockout_df["dow_label"] = stockout_df["dow"].map(dow_labels)
            stockout_dow = (
                stockout_df.groupby(["dow", "dow_label"])
                .size().reset_index(name="stockout_events")
                .sort_values("dow")
            )

        rc1, rc2 = st.columns(2)
        with rc1:
            fig_dow = px.bar(
                dow_by_machine, x="dow_label", y="total_qty", color="machine",
                barmode="group",
                title="Avg Units Sold by Day of Week",
                category_orders={"dow_label": list(dow_labels.values())},
                color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C"],
            )
            fig_dow.update_layout(xaxis_title="", yaxis_title="Avg Units/Day")
            st.plotly_chart(fig_dow, use_container_width=True)

        with rc2:
            if not stockout_df.empty:
                fig_so_dow = px.bar(
                    stockout_dow, x="dow_label", y="stockout_events",
                    title="Stock-out Events by Day of Week",
                    category_orders={"dow_label": list(dow_labels.values())},
                    color_discrete_sequence=[ACCENT],
                )
                fig_so_dow.update_layout(xaxis_title="", yaxis_title="Stock-out Count")
                st.plotly_chart(fig_so_dow, use_container_width=True)
            else:
                st.info("No stock-out data to show.")

        # Derive a recommendation: peak sales day per machine → suggest refilling the day before
        peak_days = (
            sales_df.groupby(["machine", "dow", "dow_label"])["total_qty"]
            .mean().reset_index()
            .sort_values("total_qty", ascending=False)
            .groupby("machine").first().reset_index()
        )
        st.markdown("**Refill recommendations based on your sales pattern:**")
        for _, row in peak_days.iterrows():
            peak_dow = int(row["dow"])
            refill_dow = dow_labels[(peak_dow - 1) % 7]
            st.markdown(
                f"- **{row['machine']}**: peak sales on **{row['dow_label']}** → "
                f"refill by **{refill_dow}** morning"
            )

    st.divider()

    # ---- 7c. Machine efficiency scorecard ----
    st.subheader("📊 Machine Efficiency Scorecard")
    st.caption("How each machine compares across sales, refill frequency, and stock-out rate.")

    if "machine" in sales_df.columns:
        scorecard = sales_df.groupby("machine").agg(
            total_sales=("total_sales", "sum"),
            total_qty=("total_qty", "sum"),
            active_days=("date", "nunique"),
        ).reset_index()
        scorecard["avg_daily_sales"] = (
            scorecard["total_sales"] / scorecard["active_days"]
        ).round(0)

        refill_counts = refill_df.groupby(
            refill_df["date"].dt.to_period("W")
        ).size().reset_index(name="refills_per_week") if not refill_df.empty else pd.DataFrame()

        if "machine" in stockout_df.columns:
            so_counts = (
                stockout_df.groupby("machine").size().reset_index(name="stockout_events")
            )
            scorecard = scorecard.merge(so_counts, on="machine", how="left")
            scorecard["stockout_events"] = scorecard["stockout_events"].fillna(0).astype(int)
            scorecard["stockout_rate"] = (
                scorecard["stockout_events"] / scorecard["active_days"]
            ).round(2)
        else:
            scorecard["stockout_events"] = 0
            scorecard["stockout_rate"] = 0.0

        display_cols = {
            "machine": "Machine",
            "total_sales": "Total Sales (₹)",
            "avg_daily_sales": "Avg Daily Sales (₹)",
            "total_qty": "Units Sold",
            "active_days": "Active Days",
            "stockout_events": "Stock-out Events",
            "stockout_rate": "Stock-outs / Day",
        }
        st.dataframe(
            scorecard.rename(columns=display_cols)[list(display_cols.values())]
            .sort_values("Total Sales (₹)", ascending=False),
            use_container_width=True, hide_index=True,
        )

        fig_sc = px.scatter(
            scorecard,
            x="avg_daily_sales", y="stockout_rate",
            size="total_qty", color="machine", text="machine",
            title="Avg Daily Sales vs Stock-out Rate (bubble = units sold)",
            color_discrete_sequence=[PRIMARY, ACCENT, "#6C8EBF", "#B85C5C"],
        )
        fig_sc.update_traces(textposition="top center")
        fig_sc.update_layout(xaxis_title="Avg Daily Sales (₹)", yaxis_title="Stock-outs per Day")
        st.plotly_chart(fig_sc, use_container_width=True)
        st.caption(
            "Machines in the top-left (high sales, low stock-outs) are running well. "
            "Top-right means high sales but frequent stock-outs — prioritise refilling these."
        )