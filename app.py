import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Sales Command Center", page_icon="🚀", layout="wide")

ALIASES = {
    "date": ["date","order_date","sales_date","invoice_date","transaction_date"],
    "product": ["product","product_name","item","item_name","sku","sku_name"],
    "revenue": ["revenue","sales_amount","amount","net_sales","total_amount","total_sales"],
    "units": ["units","quantity","qty","sales","units_sold"],
    "category": ["category","product_category","segment"],
    "region": ["region","territory","area"],
    "channel": ["channel","sales_channel","source"],
}

def normalize_columns(df):
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ","_") for c in df.columns]
    rename = {}
    for target, aliases in ALIASES.items():
        if target not in df.columns:
            for alias in aliases:
                if alias in df.columns:
                    rename[alias] = target
                    break
    return df.rename(columns=rename)

def prepare(df):
    df = normalize_columns(df)
    missing = [x for x in ["date","revenue","product"] if x not in df.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    if "units" not in df.columns:
        df["units"] = 0
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0)
    df["units"] = pd.to_numeric(df["units"], errors="coerce").fillna(0)
    df = df.dropna(subset=["date"]).copy()
    df["product"] = df["product"].astype(str)
    for c, default in [("category","Uncategorized"),("region","All Regions"),("channel","All Channels")]:
        if c not in df.columns: df[c] = default
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["quarter"] = df["date"].dt.to_period("Q").astype(str)
    return df

@st.cache_data
def read_database(conn_string, query):
    engine = create_engine(conn_string)
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)

def money(x):
    return f"₹{x:,.0f}"

st.title("🚀 Sales Command Center")
st.caption("Executive-style sales and revenue analysis")

with st.sidebar:
    st.header("1. Load data")
    source = st.radio("Source", ["Excel / CSV", "Database"])
    data = None
    if source == "Excel / CSV":
        uploaded = st.file_uploader("Choose a file", type=["csv","xlsx","xls"])
        if uploaded:
            try:
                raw = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded)
                data = prepare(raw)
                st.success(f"Loaded {len(data):,} rows")
            except Exception as e:
                st.error(str(e))
    else:
        conn = st.text_input("SQLAlchemy connection", type="password",
            placeholder="postgresql+psycopg2://user:password@host:5432/db")
        query = st.text_area("SQL query", "SELECT * FROM sales", height=100)
        if st.button("Connect & load", type="primary") and conn:
            try:
                st.session_state["db_data_v2"] = prepare(read_database(conn, query))
            except Exception as e:
                st.error(f"Database error: {e}")
        data = st.session_state.get("db_data_v2")

if data is None:
    st.info("Upload an Excel/CSV file or connect a database to start.")
    st.markdown("**Required:** Date, Revenue, Product.  **Optional:** Units/Quantity, Category, Region, Channel.")
    st.stop()

with st.sidebar:
    st.divider()
    st.header("2. Interactive slicers")
    start, end = data.date.min().date(), data.date.max().date()
    date_filter = st.date_input("Date range", (start, end), min_value=start, max_value=end)
    filtered = data.copy()
    if isinstance(date_filter, tuple) and len(date_filter) == 2:
        filtered = filtered[(filtered['date'].dt.date >= date_filter[0]) & (filtered['date'].dt.date <= date_filter[1])]
    for col, label in [("category","Category"),("region","Region"),("channel","Channel")]:
        selected = st.multiselect(label, sorted(filtered[col].dropna().astype(str).unique()))
        if selected:
            filtered = filtered[filtered[col].astype(str).isin(selected)]

st.subheader("Executive overview")
revenue, units, transactions = filtered['revenue'].sum(), filtered['units'].sum(), len(filtered)
avg = revenue / transactions if transactions else 0
k1,k2,k3,k4,k5 = st.columns(5)
k1.metric("Revenue", money(revenue))
k2.metric("Units sold", f"{units:,.0f}")
k3.metric("Transactions", f"{transactions:,}")
k4.metric("Avg. transaction", money(avg))
k5.metric("Active products", f"{filtered['product'].nunique():,}")

st.divider()
left,right = st.columns([1.55,1])
with left:
    st.subheader("Revenue performance")
    mode = st.selectbox(
    "Trend view",
    ["Monthly", "Quarterly", "Daily"]
)
    if mode == "Monthly": trend = filtered.groupby("month").revenue.sum()
    elif mode == "Quarterly": trend = filtered.groupby("quarter").revenue.sum()
    else: trend = filtered.groupby("date").revenue.sum()
    st.line_chart(trend, height=330)
with right:
    st.subheader("Revenue mix")
    mix_dim = st.selectbox("View mix by", ["Category","Region","Channel"])
    mix = filtered.groupby(mix_dim.lower()).revenue.sum().sort_values(ascending=False)
    st.bar_chart(mix, height=330)

st.divider()
left,right = st.columns([1.4,1])
with left:
    st.subheader("Top products")
    top_n = st.slider("Show top products", 5, 15, 8)
    top = filtered.groupby("product").agg(Revenue=("revenue","sum"), Units=("units","sum"), Transactions=("revenue","size")).sort_values("Revenue", ascending=False).head(top_n)
    st.bar_chart(top["Revenue"], height=360)
with right:
    st.subheader("Product leaderboard")
    display = top.copy()
    display["Revenue"] = display["Revenue"].map(money)
    st.dataframe(display, use_container_width=True, height=360)

st.divider()
st.subheader("Drill-down analysis")
c1,c2 = st.columns(2)
with c1: dimension = st.selectbox("Analyze dimension", ["Category","Region","Channel","Product"])
with c2: metric = st.selectbox("Measure", ["Revenue","Units","Transactions"])
col = dimension.lower()
if metric == "Revenue": drill = filtered.groupby(col).revenue.sum().sort_values(ascending=False)
elif metric == "Units": drill = filtered.groupby(col).units.sum().sort_values(ascending=False)
else: drill = filtered.groupby(col).size().sort_values(ascending=False)
st.bar_chart(drill, height=320)

with st.expander("View filtered transactions"):
    st.dataframe(filtered.sort_values("date", ascending=False), use_container_width=True, height=350)

st.download_button("⬇️ Export filtered data", filtered.to_csv(index=False).encode(), "sales_command_center_filtered.csv", "text/csv")
st.caption(f"Showing {len(filtered):,} filtered records from {len(data):,} loaded records.")
