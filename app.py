import os

import pandas as pd
import streamlit as st

# Bridge Streamlit Cloud secrets into env vars so config.load() works unchanged
# in both local (.env via python-dotenv) and Cloud (st.secrets) deployments.
# Wrapped in try/except because st.secrets raises if no secrets file exists locally.
try:
    _secrets = dict(st.secrets)
except Exception:
    _secrets = {}
_KEYS = ("SUNSYNK_USERNAME", "SUNSYNK_PASSWORD", "GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SHEET_ID")
for _key in _KEYS:
    if _key not in os.environ and _key in _secrets:
        os.environ[_key] = str(_secrets[_key])

from pipeline import config, sheets  # noqa: E402

st.set_page_config(page_title="Sunsynk", layout="wide", page_icon="⚡")

WINDOWS = {
    "1 hour": 12,
    "6 hours": 72,
    "24 hours": 288,
    "7 days": 2016,
    "30 days": 8640,
}
TZ = "Africa/Johannesburg"
NON_NUMERIC = {"inverter_sn", "model", "sw_ver", "hw_ver", "hmi_ver", "updated_at"}


@st.cache_resource
def _spreadsheet():
    cfg = config.load()
    return sheets.open_sheet(cfg.google_service_account_info, cfg.google_sheet_id)


@st.cache_data(ttl=300)
def load_tab(tab: str, last_n: int) -> pd.DataFrame:
    rows = sheets.read_recent(_spreadsheet(), tab, last_n)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    df["timestamp_sast"] = df["timestamp_utc"].dt.tz_convert(TZ)
    for col in df.columns:
        if col not in NON_NUMERIC and col not in ("timestamp_utc", "timestamp_sast"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.set_index("timestamp_sast")


def metric(col, label: str, value, unit: str = "", fmt: str = "{:.0f}") -> None:
    if value is None or pd.isna(value):
        col.metric(label, "—")
    else:
        col.metric(label, fmt.format(value) + unit)


# --- Sidebar ---
st.sidebar.title("⚡ Sunsynk")
window_label = st.sidebar.selectbox("Time window", list(WINDOWS), index=2)
last_n = WINDOWS[window_label]
st.sidebar.caption("Cache TTL is 5 minutes. Click 'Refresh' to clear.")
if st.sidebar.button("Refresh"):
    st.cache_data.clear()
    st.rerun()

# --- Load ---
try:
    battery = load_tab("battery", last_n)
    grid = load_tab("grid", last_n)
    pv = load_tab("pv", last_n)
    load = load_tab("load", last_n)
    inverter = load_tab("inverter", last_n)
except config.MissingEnvError as e:
    st.error(f"Configuration error: {e}")
    st.stop()
except Exception as e:
    st.error(f"Failed to read sheet: {e}")
    st.stop()

if battery.empty:
    st.warning("No data in the sheet yet. The cron writes every 5 minutes — give it a moment.")
    st.stop()

# --- Current state ---
latest_t = battery.index[-1]
st.title(f"Sunsynk — {window_label}")
st.caption(f"Latest reading: {latest_t.strftime('%Y-%m-%d %H:%M %Z')} · {len(battery)} rows")

c1, c2, c3, c4, c5 = st.columns(5)
metric(c1, "Battery SOC", battery["soc_pct"].iloc[-1], "%")
metric(c2, "PV", pv["power_w"].iloc[-1], " W")
metric(c3, "Grid", grid["power_w"].iloc[-1], " W")
metric(c4, "Load", load["power_w"].iloc[-1], " W")
metric(c5, "Battery temp", battery["temp_c"].iloc[-1], " °C", fmt="{:.1f}")

# --- Tabs ---
tab_overview, tab_battery, tab_pv, tab_grid, tab_load = st.tabs(
    ["Overview", "Battery", "PV", "Grid", "Load"]
)

with tab_overview:
    st.subheader("Power flow")
    flow = pd.DataFrame({
        "Battery (W)": battery["power_w"],
        "PV (W)": pv["power_w"],
        "Grid (W)": grid["power_w"],
        "Load (W)": load["power_w"],
    })
    st.line_chart(flow)
    st.caption(
        "Battery: positive = discharging, negative = charging. "
        "Grid: positive = importing, negative = exporting."
    )

with tab_battery:
    st.subheader("State of charge (%)")
    st.line_chart(battery[["soc_pct"]])
    st.subheader("Charge / discharge today (kWh, cumulative — resets at midnight UTC)")
    st.line_chart(battery[["charge_today_kwh", "discharge_today_kwh"]])
    st.subheader("Temperature (°C)")
    st.line_chart(battery[["temp_c"]])

with tab_pv:
    st.subheader("Instant PV power (W)")
    st.line_chart(pv[["power_w"]])
    st.subheader("Generation today (kWh, cumulative)")
    st.line_chart(pv[["generated_today_kwh"]])
    lifetime = pv["generated_total_kwh"].iloc[-1]
    if pd.notna(lifetime):
        st.caption(f"Lifetime generation: {lifetime:.0f} kWh")

with tab_grid:
    st.subheader("Grid power (W — positive = import)")
    st.line_chart(grid[["power_w"]])
    st.subheader("Today's import / export (kWh, cumulative)")
    st.line_chart(grid[["import_today_kwh", "export_today_kwh"]])
    cgv, cgf = st.columns(2)
    with cgv:
        st.subheader("Voltage (V)")
        st.line_chart(grid[["voltage_v"]])
    with cgf:
        st.subheader("Frequency (Hz)")
        st.line_chart(grid[["freq_hz"]])

with tab_load:
    st.subheader("Load power (W)")
    st.line_chart(load[["power_w"]])

# --- System info ---
with st.expander("System info"):
    if not inverter.empty:
        last = inverter.iloc[-1]
        st.write(f"**Inverter SN:** {last.get('inverter_sn', '—')}")
        st.write(f"**Status code:** {last.get('status', '—')}")
        st.write(f"**Software version:** {last.get('sw_ver', '—')}")
        st.write(f"**HMI version:** {last.get('hmi_ver', '—')}")
        st.write(f"**Last inverter measurement:** {last.get('updated_at', '—')}")
