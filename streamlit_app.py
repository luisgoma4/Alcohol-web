import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# Import your existing model
try:
    from alcohol_test3 import Subject, ModelOptions, simulate_brac, beverages
except Exception as e:
    st.error("Could not import 'alcohol_test3'. Make sure that alcohol_test3.py is in this folder.\n" + str(e))
    st.stop()

st.set_page_config(
    page_title="Interactive Breath Alcohol Calculator (BrAC) · Pharmacokinetic Model",
    page_icon="🍺",
    layout="wide",
)

# =========================
# Styles
# =========================
st.markdown(
    """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
h1, h2, h3 { font-weight: 700; }
div[data-testid="stMetricValue"] { font-size: 1.4rem; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🍺 Interactive Alcohol Concentration Calculator (BrAC/BAC)")
st.caption("Pharmacokinetic simulation with GI absorption → central compartment and configurable elimination.")

# =========================
# Sidebar: Presets
# =========================
st.sidebar.header("⚙️ Quick presets")
preset = st.sidebar.selectbox(
    "Initial scenario",
    [
        "Liquor on empty stomach (4×40 ml)",
        "Beer (330 ml) + meal",
        "Wine (2×150 ml, light dinner)",
        "Empty custom setup",
    ],
    index=0,
)

# =========================
# Main columns
# =========================
col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.subheader("👤 Subject data")
    c1, c2, c3, c4 = st.columns(4)
    weight_kg = c1.number_input("Weight (kg)", 40.0, 180.0, 70.0, step=1.0)
    height_cm = c2.number_input("Height (cm)", 140.0, 210.0, 175.0, step=1.0)
    age_years = c3.number_input("Age (years)", 18.0, 90.0, 35.0, step=1.0)
    sex = c4.selectbox("Sex", ["male", "female"])

    c5, c6 = st.columns(2)
    breath_temp_c = c5.slider("Exhaled air temperature (°C)", 31.0, 37.0, 34.0, 0.1)
    habitual_level = c6.slider("Habitual consumption / tolerance (0=naïve · 1=high)", 0.0, 1.0, 0.5, 0.05)

    vd_method = st.radio("Distribution volume method", ["watson", "fixed_r"], horizontal=True)
    r_widmark = st.slider("Widmark r (L/kg) · only if 'fixed_r'", 0.45, 0.80, 0.60, 0.01)

with col_right:
    st.subheader("📏 Reference limits (editable)")
    lim_col1, lim_col2 = st.columns(2)
    limit_brac = lim_col1.number_input("BrAC limit (mg/L air)", 0.05, 1.50, 0.25, 0.01)
    limit_bac = lim_col2.number_input("BAC limit (g/L blood)", 0.10, 2.00, 0.50, 0.05)

    st.subheader("⏱️ Simulation time")
    dur_col1, dur_col2 = st.columns(2)
    duration_h = dur_col1.slider("Total duration (h)", 1.0, 24.0, 12.0, 0.5)
    dt_h = dur_col2.select_slider("Time resolution", options=[0.01, 0.005, 0.0025, 0.001], value=0.0025)
    st.caption("Tip: 0.0025 h ≈ 9 s per step (good precision).")

# =========================
# Advanced panel
# =========================
with st.expander("🧪 Advanced model parameters (absorption, elimination, BBR) and reference tables", expanded=False):
    st.markdown("**Absorption** (first order from GI):")
    a1, a2, a3 = st.columns(3)
    ka_h = a1.number_input("Base ka (h⁻¹)", 0.1, 8.0, 2.4, 0.1)
    food_factor = a2.slider("Meal factor (↓ absorption)", 0.3, 1.3, 0.8, 0.05)
    carbonation_factor = a3.slider("Carbonation factor (↑ absorption)", 0.7, 1.5, 1.1, 0.05)

    st.markdown("---")
    st.markdown("**Elimination** (choose mode):")
    elimination_mode = st.radio(
        "Elimination mode",
        ["mm", "zero", "ke"],
        index=0,
        help="mm=Michaelis–Menten; zero=zero order; ke=first order",
    )

    e1, e2, e3, e4 = st.columns(4)
    Vmax_g_per_L_h = e1.number_input("Vmax (g/L·h)", 0.05, 0.60, 0.20, 0.01)
    Km_g_per_L = e2.number_input("Km (g/L)", 0.02, 0.60, 0.15, 0.01)
    beta_g_per_L_h = e3.number_input("β (g/L·h) (zero order)", 0.05, 0.60, 0.18, 0.01)
    ke_h = e4.number_input("ke (h⁻¹) (first order)", 0.05, 0.60, 0.15, 0.01)

    st.markdown("---")
    st.markdown("**Blood:Breath Ratio (BBR)**:")
    b1, b2 = st.columns(2)
    BBR_base = b1.number_input("Base BBR", 1500.0, 3000.0, 2100.0, 50.0)
    bbr_temp_coeff_per_deg = b2.number_input("Thermal coefficient per °C (≈ −0.065 optional)", -0.20, 0.20, 0.00, 0.005)

    st.markdown("---")
    st.markdown("**Reference tables**")
    df_abs = pd.DataFrame(
        {
            "Condition": ["Fasting", "Light meal", "Heavy meal", "Highly carbonated", "Non-carbonated"],
            "Typical ka (h⁻¹)": [3.0, 2.0, 1.2, 1.2, 1.0],
            "Meal factor": [1.0, 0.8, 0.6, None, None],
            "Carbonation factor": [None, None, None, 1.2, 1.0],
        }
    )
    st.dataframe(df_abs, use_container_width=True)

    df_elim = pd.DataFrame(
        {
            "Mode": ["Michaelis–Menten", "Zero order", "First order"],
            "Key parameters": ["Vmax, Km", "β", "ke"],
            "Notes": [
                "Saturable; more realistic at high concentrations",
                "Fixed elimination rate (classical clinical approximation)",
                "Proportional to concentration; useful at low concentrations",
            ],
        }
    )
    st.dataframe(df_elim, use_container_width=True)

# =========================
# Dose presets
# =========================
def preset_doses(name: str):
    if name == "Liquor on empty stomach (4×40 ml)":
        base = [
            {"t_ingesta_h": 0.00, "volumen_ml": 40, "tipo_bebida": "liquor", "ka_scale": 1.0},
            {"t_ingesta_h": 0.75, "volumen_ml": 40, "tipo_bebida": "liquor", "ka_scale": 1.0},
            {"t_ingesta_h": 1.50, "volumen_ml": 40, "tipo_bebida": "liquor", "ka_scale": 1.0},
            {"t_ingesta_h": 2.15, "volumen_ml": 40, "tipo_bebida": "liquor", "ka_scale": 1.0},
        ]
        return base, dict(food_factor=0.8, carbonation_factor=1.1)
    elif name == "Beer (330 ml) + meal":
        base = [{"t_ingesta_h": 0.00, "volumen_ml": 330, "tipo_bebida": "beer", "ka_scale": 0.9}]
        return base, dict(food_factor=0.7, carbonation_factor=1.2)
    elif name == "Wine (2×150 ml, light dinner)":
        base = [
            {"t_ingesta_h": 0.00, "volumen_ml": 150, "tipo_bebida": "wine", "ka_scale": 1.0},
            {"t_ingesta_h": 0.75, "volumen_ml": 150, "tipo_bebida": "wine", "ka_scale": 1.0},
        ]
        return base, dict(food_factor=0.8, carbonation_factor=1.0)
    else:
        return ([{"t_ingesta_h": 0.00, "volumen_ml": 40, "tipo_bebida": "liquor", "ka_scale": 1.0}], {})

base_doses, preset_opt_overrides = preset_doses(preset)

# =========================
# Dose editor table
# =========================
st.subheader("🍷 Intake pattern (editable)")
st.caption(
    "Edit times (h), volumes, and beverage type. Add or delete rows. `tipo_bebida` must exist in the catalog: "
    + ", ".join(f"{k} ({int(v*100)}%)" for k, v in beverages.items())
)

edited_df = st.data_editor(
    pd.DataFrame(base_doses),
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "t_ingesta_h": st.column_config.NumberColumn("t_ingesta_h (h)", step=0.05, help="Relative time from t=0"),
        "volumen_ml": st.column_config.NumberColumn("volume (ml)", step=5),
        "tipo_bebida": st.column_config.TextColumn("beverage_type", help="e.g., beer, wine, liquor"),
        "ka_scale": st.column_config.NumberColumn("ka_scale", step=0.05, help="Local ka adjustment for that intake"),
    },
)

# =========================
# Model object construction
# =========================
if preset_opt_overrides:
    food_factor = preset_opt_overrides.get("food_factor", food_factor)
    carbonation_factor = preset_opt_overrides.get("carbonation_factor", carbonation_factor)

subject = Subject(
    weight_kg=weight_kg,
    height_cm=height_cm,
    age_years=age_years,
    sex=sex,
    breath_temp_c=breath_temp_c,
    habitual_level=habitual_level,
    vd_method=vd_method,
    r_widmark=r_widmark,
)

options = ModelOptions(
    ka_h=ka_h,
    food_factor=food_factor,
    carbonation_factor=carbonation_factor,
    elimination_mode=elimination_mode,
    Vmax_g_per_L_h=Vmax_g_per_L_h,
    Km_g_per_L=Km_g_per_L,
    beta_g_per_L_h=beta_g_per_L_h,
    ke_h=ke_h,
    BBR_base=BBR_base,
    bbr_temp_coeff_per_deg=bbr_temp_coeff_per_deg,
)

# =========================
# Prepare dose tuples for engine
# =========================
doses = []
for _, row in edited_df.iterrows():
    t_h = float(row["t_ingesta_h"])
    vol = float(row["volumen_ml"])
    tipo = str(row["tipo_bebida"]).strip().lower()
    ka_scale = float(row.get("ka_scale", 1.0))
    doses.append((t_h, vol, tipo, {"ka_scale": ka_scale}))

invalid = [d for d in doses if d[1] <= 0 or d[0] < 0 or d[2] not in beverages]
if invalid:
    st.error("Invalid rows in table (volume ≤ 0, time < 0 or beverage not in catalog). Correct before running simulation.")
    st.stop()

# =========================
# Simulation
# =========================
times, BAC, BrAC = simulate_brac(
    subject=subject,
    doses=doses,
    opts=options,
    duration_h=duration_h,
    dt_h=dt_h,
)

# =========================
# Quick metrics
# =========================
idx_max = int(np.argmax(BrAC))
brac_max = float(BrAC[idx_max])
tmax = float(times[idx_max])

m1, m2, m3 = st.columns(3)
m1.metric("Max BrAC (mg/L air)", f"{brac_max:.3f}", help="Peak alcohol concentration in exhaled air")
m2.metric("t(peak) (h)", f"{tmax:.2f}")
m3.metric("BAC at peak (g/L)", f"{float(BAC[idx_max]):.3f}")

# =========================
# Graphs
# =========================
st.subheader("📈 Results")

fig_brac = px.line(x=times, y=BrAC, labels={"x": "Time (h)", "y": "BrAC (mg/L air)"}, title="BrAC vs Time")
fig_brac.add_hline(y=limit_brac, line_dash="dash", annotation_text=f"BrAC limit = {limit_brac:.2f} mg/L")
st.plotly_chart(fig_brac, use_container_width=True, theme="streamlit")

fig_bac = px.line(x=times, y=BAC, labels={"x": "Time (h)", "y": "BAC (g/L)"}, title="BAC vs Time")
fig_bac.add_hline(y=limit_bac, line_dash="dash", annotation_text=f"BAC limit = {limit_bac:.2f} g/L")
st.plotly_chart(fig_bac, use_container_width=True, theme="streamlit")

# =========================
# Data export
# =========================
st.subheader("💾 Export data")
out_df = pd.DataFrame({"t_h": times, "BAC_g_per_L": BAC, "BrAC_mg_per_L": BrAC})
csv = out_df.to_csv(index=False).encode("utf-8")
st.download_button("Download CSV (t, BAC, BrAC)", data=csv, file_name="brac_bac_simulation.csv", mime="text/csv")

# =========================
# Help / Notes
# =========================
with st.expander("ℹ️ Model notes and responsible use"):
    st.markdown(
        """
- The model uses **first-order absorption** from the GI tract and configurable elimination (**Michaelis–Menten**, **zero order**, or **first order**).
- **Tolerance/habitual consumption** adjusts elimination parameters (↑Vmax/β, slight Km variation) as a practical approximation.
- **BBR** (blood:breath ratio) default = 2100, with optional thermal correction for exhaled air.
- Legal limits may vary by country and condition; these are **editable fields**.
- This tool is educational and **not** a substitute for official testing or medical/legal advice.
        """
    )
