import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass

# ================================================================
# Utilidades fisiológicas
# ================================================================

def grams_of_ethanol(volume_ml: float, abv: float) -> float:
    """Devuelve gramos de etanol a partir de volumen (ml) y ABV (fracción 0-1)."""
    density_ethanol = 0.789  # g/ml
    return volume_ml * abv * density_ethanol


def watson_tbw_liters(sex: str, age: float, height_cm: float, weight_kg: float) -> float:
    """Agua corporal total (TBW) en litros, fórmulas de Watson (aprox.).
    Referencia: Watson et al., ampliamente usada en clínica.
    """
    sex = sex.lower()
    height_m = height_cm / 100.0
    if sex in ("m", "male", "h", "hombre"):
        tbw = 2.447 - 0.09516 * age + 0.1074 * height_cm + 0.3362 * weight_kg
    else:  # mujer por defecto
        tbw = -2.097 + 0.1069 * height_cm + 0.2466 * weight_kg
    return float(tbw)  # litros


# ================================================================
# Parámetros del sujeto y del modelo
# ================================================================

@dataclass
class Subject:
    weight_kg: float
    height_cm: float
    age_years: float
    sex: str  # 'male'/'female'
    breath_temp_c: float = 34.0  # temperatura de aire espirado nominal
    habitual_level: float = 0.0  # 0.0 (naïve) – 1.0 (consumo crónico)

    # Volumen de distribución
    vd_method: str = "watson"  # 'watson' | 'fixed_r'
    r_widmark: float = 0.6  # solo si vd_method == 'fixed_r', L/kg

    def Vd_liters(self) -> float:
        if self.vd_method == "watson":
            return watson_tbw_liters(self.sex, self.age_years, self.height_cm, self.weight_kg)
        else:
            return self.r_widmark * self.weight_kg


@dataclass
class ModelOptions:
    # Absorción
    ka_h: float = 2.4         # h^-1 (ayuno). Se ajustará por comida/carbonatación.
    food_factor: float = 1.0  # <1.0 si con comida (p.ej. 0.6), >1.0 si ayuno muy rápido
    carbonation_factor: float = 1.0  # >1.0 para bebidas muy carbonatadas

    # Eliminación (elegir uno en elimination_mode)
    elimination_mode: str = "mm"  # 'mm' | 'zero' | 'ke'
    # Michaelis–Menten (valores por defecto razonables)
    Vmax_g_per_L_h: float = 0.20  # velocidad máx. por litro de distribución
    Km_g_per_L: float = 0.15
    # Orden cero
    beta_g_per_L_h: float = 0.18
    # Primer orden
    ke_h: float = 0.15

    # BrAC: relación sangre:aliento (BBR)
    BBR_base: float = 2100.0
    bbr_temp_coeff_per_deg: float = 0.0  # opcional: ~ -0.065 por °C si se desea usar


# ================================================================
# Catálogo de bebidas
# ================================================================

beverages = {
    'beer': 0.05
    'wine': 0.12
    'liquor': 0.40
    'absenta': 0.9
    'absinthe': 0.9
    'cerveza': 0.05,
    'vino': 0.12,
    'licor': 0.45,
    'chupito': 0.3,
    'shot': 0.3
    # puedes añadir más: 'cava': 0.115, 'refresco+vodka': 0.40, etc.
}


# ================================================================
# Núcleo de simulación (dos compartimentos: GI -> central)
# ================================================================

def simulate_brac(
    subject: Subject,
    doses,
    opts: ModelOptions,
    duration_h: float = 8.0,
    dt_h: float = 0.0025,
):
    """
    Simula BAC y BrAC con absorción 1º orden desde compartimento GI y
    eliminación configurable (MM, cero-orden, o 1er orden) en compartimento central.

    Parameters
    ----------
    subject : Subject
        Parámetros individuales del sujeto (Vd, tolerancia, etc.).
    doses : list of tuples
        [(t_ingesta_h, volumen_ml, tipo_bebida:str, opciones_dict_opcional), ...]
        donde opciones_dict_opcional puede incluir: {'abv': 0.12, 'ka_scale': 0.9}
    opts : ModelOptions
        Parámetros del modelo farmacocinético.
    duration_h : float
        Tiempo total simulado (h).
    dt_h : float
        Paso temporal (h). ~0.0025 h ≈ 9 s

    Returns
    -------
    times_h : np.ndarray
    BAC_g_per_L : np.ndarray
    BrAC_mg_per_L : np.ndarray
    """
    Vd = subject.Vd_liters()

    # Ajustes de absorción globales
    base_ka = opts.ka_h * opts.food_factor * opts.carbonation_factor

    # Preparar dosis en el compartimento GI (gramos)
    dose_list = []
    for tup in doses:
        if len(tup) == 3:
            t_dose, vol_ml, tipo = tup
            abv = beverages.get(tipo, None)
            if abv is None:
                raise ValueError(f"Tipo de bebida desconocido: {tipo}")
            local_opts = {}
        else:
            t_dose, vol_ml, tipo, local_opts = tup
            abv = local_opts.get('abv', beverages.get(tipo, None))
            if abv is None:
                raise ValueError(f"Tipo de bebida desconocido: {tipo}")
        grams = grams_of_ethanol(vol_ml, abv)
        ka_local = base_ka * float(local_opts.get('ka_scale', 1.0))
        dose_list.append({'t': float(t_dose), 'Ag': 0.0, 'D': grams, 'ka': ka_local, 'loaded': False})

    # Ajuste por tolerancia/consumo habitual (↑Vmax o ↑beta; ↓Km)
    tol = float(np.clip(subject.habitual_level, 0.0, 1.0))
    Vmax = opts.Vmax_g_per_L_h * (1.0 + 0.6 * tol)  # hasta +60%
    Km = max(1e-6, opts.Km_g_per_L * (1.0 + 0.2 * tol))  # ligera variación
    beta = opts.beta_g_per_L_h * (1.0 + 0.4 * tol)
    ke = opts.ke_h

    # BBR efectivo con posible corrección térmica
    BBR = opts.BBR_base * (1.0 + opts.bbr_temp_coeff_per_deg * (subject.breath_temp_c - 34.0))
    BBR = max(1000.0, BBR)  # evitar valores extremos

    n = int(np.ceil(duration_h / dt_h))
    times = np.linspace(0.0, duration_h, n, endpoint=False)

    A_c = 0.0  # gramos en compartimento central
    BAC = np.zeros_like(times)

    # Integración explícita (Euler) suficiente para dt pequeño
    for i, t in enumerate(times):
        # Cargar dosis al llegar su tiempo
        for d in dose_list:
            if (not d['loaded']) and (t >= d['t']):
                d['Ag'] = d['Ag'] + d['D']
                d['loaded'] = True

        # Absorción total desde GI
        absorption_g_per_h = 0.0
        for d in dose_list:
            if d['Ag'] > 0.0:
                rate = d['ka'] * d['Ag']
                # actualizar GI para siguiente paso
                d['Ag'] -= rate * dt_h
                if d['Ag'] < 0.0:
                    rate += d['Ag'] / dt_h  # corregir pequeña sobre-resta
                    d['Ag'] = 0.0
                absorption_g_per_h += rate

        # Eliminación desde el compartimento central según modo
        C = A_c / Vd  # g/L
        if opts.elimination_mode == 'mm':
            elim_rate_g_per_h = Vmax * C / (Km + C) * Vd  # g/h
        elif opts.elimination_mode == 'zero':
            elim_rate_g_per_h = beta * Vd
        else:  # 'ke'
            elim_rate_g_per_h = ke * A_c

        # No permitir eliminación mayor que lo disponible
        elim_rate_g_per_h = min(elim_rate_g_per_h, A_c / dt_h) if A_c > 0 else 0.0

        # Actualizar masa en compartimento central
        dA_dt = absorption_g_per_h - elim_rate_g_per_h
        A_c = max(0.0, A_c + dA_dt * dt_h)

        # Guardar BAC
        BAC[i] = A_c / Vd

    # Convertir BAC (g/L) a BrAC (mg/L aire)
    BrAC = BAC * 1000.0 / BBR
    return times, BAC, BrAC


# ================================================================
# Ejemplo de uso
# ================================================================
if __name__ == "__main__":
    # === Definir sujeto ===
    sujeto = Subject(
        weight_kg=62,
        height_cm=180,
        age_years=26,
        sex='male',
        breath_temp_c=34.0,
        habitual_level=0.5,  # consumidor habitual medio
        vd_method='watson',
        r_widmark=0.6,
    )

    # === Opciones de modelo ===
    opciones = ModelOptions(
        ka_h=2.4,
        food_factor=0.8,           # comida ligera reduce absorción
        carbonation_factor=1.1,    # bebida con algo de gas
        elimination_mode='mm',     # 'mm' | 'zero' | 'ke'
        Vmax_g_per_L_h=0.20,
        Km_g_per_L=0.15,
        beta_g_per_L_h=0.18,
        ke_h=0.15,
        BBR_base=2100.0,
        bbr_temp_coeff_per_deg=0.0 # pon -0.065 si quieres corrección térmica aproximada
    )

    # === Definir patrón de ingesta (t, ml, tipo, opciones) ===
    doses = [
        (0.0, 40, 'licor'),
        (0.75, 40, 'licor'),
        (1.50, 40, 'licor'),
        (2.15, 40, 'licor'),
        # Ejemplo con ajuste por bebida particular (p.ej., sorbo lento)
        # (0.0, 330, 'cerveza', {'ka_scale': 0.9}),
    ]

    t, BAC, BrAC = simulate_brac(sujeto, doses, opciones, duration_h=12.0, dt_h=0.0025)

    # === Gráficos ===

    plt.figure()
    plt.plot(t, BrAC, label='BrAC (mg/L)')
    plt.axhline(0.25, linestyle='--', label='Límite legal 0.25 mg/L')
    plt.xlabel('Tiempo (h)')
    plt.ylabel('BrAC (mg/L aire)')
    plt.title('Concentración de alcohol en aliento (BrAC)')
    plt.grid(True)

    plt.legend()

    plt.close

    plt.figure()
    plt.plot(t, BAC, label='BAC (g/L)')
    plt.xlabel('Tiempo (h)')
    plt.ylabel('BAC (g/L)')
    plt.title('Concentración de alcohol en sangre (BAC)')
    plt.grid(True)
    plt.axhline(0.5, color='red', linestyle='--', label='Límite legal (0.5 g/L)')

    plt.legend()



    plt.show()




    """
    sujeto = Subject(weight_kg=70, height_cm=175, age_years=35, sex='male',breath_temp_c=34.0, habitual_level=0.5, vd_method='watson')

    opciones = ModelOptions(elimination_mode='mm', Vmax_g_per_L_h=0.20, Km_g_per_L=0.15,food_factor=0.8, carbonation_factor=1.1, BBR_base=2100.0)
    
    doses = [(0.0, 40, 'licor'), (0.75, 40, 'licor'), (1.50, 40, 'licor'), (2.15, 40, 'licor')]

    opciones = ModelOptions(ka_h=2.4, food_factor=0.8, carbonation_factor=1.1,elimination_mode='mm', Vmax_g_per_L_h=0.20, Km_g_per_L=0.15,beta_g_per_L_h=0.18, ke_h=0.15, BBR_base=2100.0,bbr_temp_coeff_per_deg=0.0)       

    t, BAC, BrAC = simulate_brac(sujeto, doses, opciones, duration_h=12.0, dt_h=0.0025)

    
    """
