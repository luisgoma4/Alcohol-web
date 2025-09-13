#!/usr/bin/env bash
# setup_brac_app.sh — Crea todos los archivos necesarios para la app web (Streamlit + Docker)
# Uso:
#   1) Guarda este archivo como setup_brac_app.sh en esta misma carpeta
#   2) Da permisos:    chmod +x setup_brac_app.sh
#   3) Ejecuta:        ./setup_brac_app.sh
#   4) Arranca local:  streamlit run streamlit_app.py
#   5) Con Docker:     docker build -t brac-app . && docker run --rm -p 8501:8501 brac-app

set -euo pipefail

# ---- Carpetas ----
mkdir -p .streamlit assets

# ---- streamlit_app.py ----
cat > streamlit_app.py <<'PY'
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# Importa tu modelo existente
try:
    from alcohol_test3 import Subject, ModelOptions, simulate_brac, beverages
except Exception as e:
    st.error("No se pudo importar 'alcohol_test3'. Asegúrate de que alcohol_test3.py está en esta carpeta.\n" + str(e))
    st.stop()

st.set_page_config(
    page_title="Calculadora de Alcohol en Aliento (BrAC) · Interactiva",
    page_icon="🍺",
    layout="wide",
)

# =========================
# Estilos
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

st.title("🍺 Calculadora interactiva de tasa de alcohol (BrAC/BAC)")
st.caption("Simulación farmacocinética con absorción GI → compartimento central y eliminación configurable.")

# =========================
# Sidebar: Presets
# =========================
st.sidebar.header("⚙️ Presets rápidos")
preset = st.sidebar.selectbox(
    "Escenario inicial",
    [
        "Licor en ayuno (4×40 ml)",
        "Cerveza (330 ml) + comida",
        "Vino (2×150 ml, cena ligera)",
        "Personalizado vacío",
    ],
    index=0,
)

# =========================
# Columnas principales
# =========================
col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.subheader("👤 Datos del sujeto")
    c1, c2, c3, c4 = st.columns(4)
    weight_kg = c1.number_input("Peso (kg)", 40.0, 180.0, 70.0, step=1.0)
    height_cm = c2.number_input("Altura (cm)", 140.0, 210.0, 175.0, step=1.0)
    age_years = c3.number_input("Edad (años)", 18.0, 90.0, 35.0, step=1.0)
    sex = c4.selectbox("Sexo", ["male", "female"])

    c5, c6 = st.columns(2)
    breath_temp_c = c5.slider("Temperatura del aire espirado (°C)", 31.0, 37.0, 34.0, 0.1)
    habitual_level = c6.slider("Consumo habitual / tolerancia (0=naïf · 1=alto)", 0.0, 1.0, 0.5, 0.05)

    vd_method = st.radio("Volumen de distribución", ["watson", "fixed_r"], horizontal=True)
    r_widmark = st.slider("r de Widmark (L/kg) · solo si 'fixed_r'", 0.45, 0.80, 0.60, 0.01)

with col_right:
    st.subheader("📏 Límites de referencia (editables)")
    lim_col1, lim_col2 = st.columns(2)
    limit_brac = lim_col1.number_input("Límite BrAC (mg/L aire)", 0.05, 1.50, 0.25, 0.01)
    limit_bac = lim_col2.number_input("Límite BAC (g/L sangre)", 0.10, 2.00, 0.50, 0.05)

    st.subheader("⏱️ Tiempo de simulación")
    dur_col1, dur_col2 = st.columns(2)
    duration_h = dur_col1.slider("Duración total (h)", 1.0, 24.0, 12.0, 0.5)
    dt_h = dur_col2.select_slider("Resolución temporal", options=[0.01, 0.005, 0.0025, 0.001], value=0.0025)
    st.caption("Consejo: 0.0025 h ≈ 9 s por paso (buena precisión).")

# =========================
# Panel Avanzado
# =========================
with st.expander("🧪 Parámetros avanzados del modelo (absorción, eliminación, BBR) y tablas orientativas", expanded=False):
    st.markdown("**Absorción** (primer orden desde GI):")
    a1, a2, a3 = st.columns(3)
    ka_h = a1.number_input("ka (h⁻¹) base", 0.1, 8.0, 2.4, 0.1)
    food_factor = a2.slider("Factor comida (↓ absorción)", 0.3, 1.3, 0.8, 0.05)
    carbonation_factor = a3.slider("Factor carbonatación (↑ absorción)", 0.7, 1.5, 1.1, 0.05)

    st.markdown("---")
    st.markdown("**Eliminación** (elige modo):")
    elimination_mode = st.radio(
        "Modo de eliminación",
        ["mm", "zero", "ke"],
        index=0,
        help="mm=Michaelis–Menten; zero=orden cero; ke=primer orden",
    )

    e1, e2, e3, e4 = st.columns(4)
    Vmax_g_per_L_h = e1.number_input("Vmax (g/L·h)", 0.05, 0.60, 0.20, 0.01)
    Km_g_per_L = e2.number_input("Km (g/L)", 0.02, 0.60, 0.15, 0.01)
    beta_g_per_L_h = e3.number_input("β (g/L·h) (orden 0)", 0.05, 0.60, 0.18, 0.01)
    ke_h = e4.number_input("ke (h⁻¹) (1er orden)", 0.05, 0.60, 0.15, 0.01)

    st.markdown("---")
    st.markdown("**Relación sangre:aliento (BBR)**:")
    b1, b2 = st.columns(2)
    BBR_base = b1.number_input("BBR base", 1500.0, 3000.0, 2100.0, 50.0)
    bbr_temp_coeff_per_deg = b2.number_input("Coef. térmico por °C (≈ −0.065 opcional)", -0.20, 0.20, 0.00, 0.005)

    st.markdown("---")
    st.markdown("**Tablas orientativas**")
    df_abs = pd.DataFrame(
        {
            "Condición": ["Ayuno", "Comida ligera", "Comida copiosa", "Muy carbonatada", "Sin gas"],
            "ka típico (h⁻¹)": [3.0, 2.0, 1.2, 1.2, 1.0],
            "Factor comida": [1.0, 0.8, 0.6, None, None],
            "Factor carbonatación": [None, None, None, 1.2, 1.0],
        }
    )
    st.dataframe(df_abs, use_container_width=True)

    df_elim = pd.DataFrame(
        {
            "Modo": ["Michaelis–Menten", "Orden cero", "Primer orden"],
            "Parámetros clave": ["Vmax, Km", "β", "ke"],
            "Notas": [
                "Saturable; más realista a concentraciones altas",
                "Ritmo fijo de eliminación (aprox. clínica clásica)",
                "Proporcional a concentración; útil a bajas concentraciones",
            ],
        }
    )
    st.dataframe(df_elim, use_container_width=True)

# =========================
# Presets de dosis
# =========================
def preset_doses(name: str):
    if name == "Licor en ayuno (4×40 ml)":
        base = [
            {"t_ingesta_h": 0.00, "volumen_ml": 40, "tipo_bebida": "licor", "ka_scale": 1.0},
            {"t_ingesta_h": 0.75, "volumen_ml": 40, "tipo_bebida": "licor", "ka_scale": 1.0},
            {"t_ingesta_h": 1.50, "volumen_ml": 40, "tipo_bebida": "licor", "ka_scale": 1.0},
            {"t_ingesta_h": 2.15, "volumen_ml": 40, "tipo_bebida": "licor", "ka_scale": 1.0},
        ]
        return base, dict(food_factor=0.8, carbonation_factor=1.1)
    elif name == "Cerveza (330 ml) + comida":
        base = [
            {"t_ingesta_h": 0.00, "volumen_ml": 330, "tipo_bebida": "cerveza", "ka_scale": 0.9},
        ]
        return base, dict(food_factor=0.7, carbonation_factor=1.2)
    elif name == "Vino (2×150 ml, cena ligera)":
        base = [
            {"t_ingesta_h": 0.00, "volumen_ml": 150, "tipo_bebida": "vino", "ka_scale": 1.0},
            {"t_ingesta_h": 0.75, "volumen_ml": 150, "tipo_bebida": "vino", "ka_scale": 1.0},
        ]
        return base, dict(food_factor=0.8, carbonation_factor=1.0)
    else:
        return ([{"t_ingesta_h": 0.00, "volumen_ml": 40, "tipo_bebida": "licor", "ka_scale": 1.0}], {})

base_doses, preset_opt_overrides = preset_doses(preset)

# =========================
# Editor de dosis por tabla
# =========================
st.subheader("🍷 Patrón de ingesta (editable)")
st.caption(
    "Edita tiempos (h), volúmenes y tipo. Añade o borra filas. `tipo_bebida` debe estar en el catálogo: "
    + ", ".join(f"{k} ({int(v*100)}%)" for k, v in beverages.items())
)

edited_df = st.data_editor(
    pd.DataFrame(base_doses),
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "t_ingesta_h": st.column_config.NumberColumn("t_ingesta_h (h)", step=0.05, help="Hora relativa desde t=0"),
        "volumen_ml": st.column_config.NumberColumn("volumen (ml)", step=5),
        "tipo_bebida": st.column_config.TextColumn("tipo_bebida", help="p. ej., cerveza, vino, licor"),
        "ka_scale": st.column_config.NumberColumn("ka_scale", step=0.05, help="Ajuste local de ka para esa ingesta"),
    },
)

# =========================
# Construcción de objetos del modelo
# =========================
if preset_opt_overrides:
    food_factor = preset_opt_overrides.get("food_factor", food_factor)
    carbonation_factor = preset_opt_overrides.get("carbonation_factor", carbonation_factor)

sujeto = Subject(
    weight_kg=weight_kg,
    height_cm=height_cm,
    age_years=age_years,
    sex=sex,
    breath_temp_c=breath_temp_c,
    habitual_level=habitual_level,
    vd_method=vd_method,
    r_widmark=r_widmark,
)

opciones = ModelOptions(
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
# Preparar tupla de dosis para el motor
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
    st.error("Hay filas inválidas en la tabla (volumen ≤ 0, tiempo < 0 o tipo fuera de catálogo). Corrige para simular.")
    st.stop()

# =========================
# Simulación
# =========================
times, BAC, BrAC = simulate_brac(
    subject=sujeto,
    doses=doses,
    opts=opciones,
    duration_h=duration_h,
    dt_h=dt_h,
)

# =========================
# Métricas rápidas
# =========================
idx_max = int(np.argmax(BrAC))
brac_max = float(BrAC[idx_max])
tmax = float(times[idx_max])

m1, m2, m3 = st.columns(3)
m1.metric("BrAC máx (mg/L aire)", f"{brac_max:.3f}", help="Pico de alcohol en aire espirado")
m2.metric("t(pico) (h)", f"{tmax:.2f}")
m3.metric("BAC al pico (g/L)", f"{float(BAC[idx_max]):.3f}")

# =========================
# Gráficas
# =========================
st.subheader("📈 Resultados")

fig_brac = px.line(x=times, y=BrAC, labels={"x": "Tiempo (h)", "y": "BrAC (mg/L aire)"}, title="BrAC vs tiempo")
fig_brac.add_hline(y=limit_brac, line_dash="dash", annotation_text=f"Límite BrAC = {limit_brac:.2f} mg/L")
st.plotly_chart(fig_brac, use_container_width=True, theme="streamlit")

fig_bac = px.line(x=times, y=BAC, labels={"x": "Tiempo (h)", "y": "BAC (g/L)"}, title="BAC vs tiempo")
fig_bac.add_hline(y=limit_bac, line_dash="dash", annotation_text=f"Límite BAC = {limit_bac:.2f} g/L")
st.plotly_chart(fig_bac, use_container_width=True, theme="streamlit")

# =========================
# Descarga de datos
# =========================
st.subheader("💾 Exportar datos")
out_df = pd.DataFrame({"t_h": times, "BAC_g_per_L": BAC, "BrAC_mg_per_L": BrAC})
csv = out_df.to_csv(index=False).encode("utf-8")
st.download_button("Descargar CSV (t, BAC, BrAC)", data=csv, file_name="simulacion_brac_bac.csv", mime="text/csv")

# =========================
# Ayuda / Notas
# =========================
with st.expander("ℹ️ Notas del modelo y uso responsable"):
    st.markdown(
        """
- El modelo usa **absorción de 1.º orden** desde el tracto GI y eliminación configurable (**Michaelis–Menten**, **orden cero** o **primer orden**).
- La **tolerancia/consumo habitual** ajusta parámetros de eliminación (↑Vmax/β, ligera variación de Km), como aproximación práctica.
- **BBR** (blood:breath ratio) por defecto 2100, con opción a corrección térmica del aire espirado.
- Los límites legales pueden variar por país y condición; aquí son **campos editables**.
- Esta herramienta es educativa; **no** sustituye pruebas oficiales ni asesoramiento legal o médico.
        """
    )
PY

# ---- requirements.txt ----
cat > requirements.txt <<'REQ'
streamlit>=1.36
pandas>=2.2
plotly>=5.22
numpy>=1.26
REQ

# ---- Dockerfile ----
cat > Dockerfile <<'DOCK'
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates fonts-dejavu tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY alcohol_test3.py streamlit_app.py /app/
COPY .streamlit /app/.streamlit
COPY assets /app/assets

ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

EXPOSE 8501

CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
DOCK

# ---- docker-compose.yml (opcional) ----
cat > docker-compose.yml <<'YML'
services:
  brac-app:
    build: .
    ports:
      - "8501:8501"
    environment:
      - STREAMLIT_SERVER_ADDRESS=0.0.0.0
      - STREAMLIT_SERVER_PORT=8501
    restart: unless-stopped
YML

# ---- .streamlit/config.toml ----
cat > .streamlit/config.toml <<'TOML'
[theme]
base="light"
primaryColor="#0f766e"
backgroundColor="#ffffff"
secondaryBackgroundColor="#f6f9fb"
textColor="#0b1221"
font="sans serif"

[server]
enableCORS = false
enableXsrfProtection = true
headless = true
port = 8501
address = "0.0.0.0"

[browser]
gatherUsageStats = false
TOML

# ---- assets de ejemplo (opcionales) ----
cat > assets/README.txt <<'ASSET'
Coloca aquí logo.png y favicon.png si deseas branding propio.
ASSET

# ---- README rápido ----
cat > README.md <<'MD'
# Calculadora de BrAC/BAC — Streamlit + Docker

## Uso rápido
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Docker
```bash
docker build -t brac-app .
docker run --rm -p 8501:8501 brac-app
```

## Notas
- Asegúrate de que `alcohol_test3.py` está en la raíz del proyecto.
- Edita `.streamlit/config.toml` para el tema visual.
MD

# Mensaje final
cat <<'EOM'
✅ Archivos creados.
Siguiente paso:
  1) Si no lo has hecho: chmod +x setup_brac_app.sh && ./setup_brac_app.sh
  2) Ejecuta local:    streamlit run streamlit_app.py
  3) Docker:           docker build -t brac-app . && docker run --rm -p 8501:8501 brac-app
EOM
