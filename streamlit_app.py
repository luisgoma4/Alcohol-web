import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import storage
from config import (
    ADVANCED_DEFAULTS,
    DEFAULTS,
    DRINKS,
    FOOD_FACTORS,
    LIMITS,
    QUICK_DRINKS,
    STORAGE_KEY,
)
from i18n import LANGUAGES, translator

try:
    from alcohol_test3 import ModelOptions, Subject, simulate_brac
except Exception as e:
    st.error("Could not import 'alcohol_test3'. Make sure that alcohol_test3.py is in this folder.\n" + str(e))
    st.stop()

ss = st.session_state

# =========================
# Time helpers (drinks are entered as clock times in the user's time zone)
# =========================
def _tz():
    try:
        return ZoneInfo(st.context.timezone) if st.context.timezone else None
    except Exception:
        return None


def _now() -> dt.datetime:
    return dt.datetime.now(_tz()).replace(tzinfo=None, second=0, microsecond=0)


def _parse_time(value) -> dt.time:
    if isinstance(value, dt.time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, dt.datetime):
        return value.time().replace(second=0, microsecond=0)
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[1]
    hh, mm = text.split(":")[:2]
    return dt.time(int(hh), int(mm[:2]))


def _fmt_time(value: dt.time) -> str:
    return value.strftime("%H:%M")


def _offsets_hours(times: list[dt.time]) -> tuple[list[float], dt.time]:
    """Hours since the first drink, handling nights that cross midnight.

    The largest gap around the clock is taken as the time without drinking,
    so 23:30 → 00:30 counts as one hour later, not 23 hours earlier.
    """
    minutes = [t_.hour * 60 + t_.minute for t_ in times]
    uniq = sorted(set(minutes))
    gaps = [(uniq[(i + 1) % len(uniq)] - m) % 1440 or 1440 for i, m in enumerate(uniq)]
    start = uniq[(int(np.argmax(gaps)) + 1) % len(uniq)]
    return [((m - start) % 1440) / 60.0 for m in minutes], dt.time(start // 60, start % 60)


# =========================
# State: defaults + data remembered in the browser
# =========================
def _browser_lang() -> str:
    locale = (st.context.locale or "").lower()
    return "es" if locale.startswith("es") or not locale else "en"


def _set_defaults(force: bool = False):
    base = dict(DEFAULTS, lang=ss.get("lang", _browser_lang()))
    for k, v in base.items():
        if force or k not in ss:
            ss[k] = v
    for k, v in ADVANCED_DEFAULTS.items():
        if force or f"adv_{k}" not in ss:
            ss[f"adv_{k}"] = v
    if force or "drinks" not in ss:
        ss.drinks = []
    ss.setdefault("editor_ver", 0)


# Allowed values (choices or numeric ranges) for anything read back from the browser
VALID = {
    "lang": list(LANGUAGES),
    "sex": ["male", "female"],
    "food": list(FOOD_FACTORS),
    "limit_profile": ["general", "novice", "custom"],
    "age_years": (18, 100),
    "weight_kg": (35, 200),
    "height_cm": (130, 220),
    "limit_brac": (0.0, 1.5),
    "limit_bac": (0.0, 3.0),
    "adv_habitual_level": (0.0, 1.0),
    "adv_carbonation_factor": (0.7, 1.5),
    "adv_breath_temp_c": (31.0, 37.0),
    "adv_dt_h": (0.001, 0.01),
    "adv_vd_method": ["watson", "fixed_r"],
    "adv_r_widmark": (0.45, 0.80),
    "adv_ka_h": (0.1, 8.0),
    "adv_elimination_mode": ["mm", "zero", "ke"],
    "adv_Vmax_g_per_L_h": (0.05, 0.60),
    "adv_Km_g_per_L": (0.02, 0.60),
    "adv_beta_g_per_L_h": (0.05, 0.60),
    "adv_ke_h": (0.05, 0.60),
    "adv_BBR_base": (1500.0, 3000.0),
    "adv_bbr_temp_coeff_per_deg": (-0.20, 0.20),
}


def _valid(key: str, value) -> bool:
    rule = VALID[key]
    if isinstance(rule, list):
        return value in rule
    return isinstance(value, (int, float)) and not isinstance(value, bool) and rule[0] <= value <= rule[1]


def _apply_saved(data: dict):
    """Copy remembered values into the session, ignoring anything malformed."""
    for k, v in data.items():
        if k in VALID and _valid(k, v):
            ss[k] = type(DEFAULTS[k])(v)
    for k, v in (data.get("advanced") or {}).items():
        if f"adv_{k}" in VALID and _valid(f"adv_{k}", v):
            ss[f"adv_{k}"] = type(ADVANCED_DEFAULTS[k])(v)
    drinks = []
    for d in data.get("drinks") or []:
        try:
            if d["drink"] in DRINKS:
                _parse_time(d["time"])
                drinks.append({"time": d["time"], "drink": d["drink"], "ml": float(d["ml"]), "abv": float(d["abv"])})
        except (KeyError, TypeError, ValueError):
            continue
    ss.drinks = drinks
    ss.editor_ver += 1


def _payload() -> dict:
    data = {k: ss[k] for k in DEFAULTS}
    if ss.limit_profile != "custom":
        data.pop("limit_brac")
        data.pop("limit_bac")
    data["drinks"] = ss.drinks
    data["advanced"] = {k: ss[f"adv_{k}"] for k, v in ADVANCED_DEFAULTS.items() if ss[f"adv_{k}"] != v}
    return data


_set_defaults()
saved = storage.load(STORAGE_KEY)
if saved:
    _apply_saved(saved)
if not storage.is_ready():
    # Wait for the browser to hand over the saved data before drawing any widget;
    # it arrives almost instantly and triggers a rerun.
    st.stop()

t = translator(ss.lang)

st.set_page_config(page_title=t("page_title"), page_icon="🍺", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1100px;}
h1, h2, h3 { font-weight: 700; }
div[data-testid="stMetricValue"] { font-size: 1.5rem; }
</style>
""",
    unsafe_allow_html=True,
)

def _sort_drinks():
    if ss.drinks:
        offs, _ = _offsets_hours([_parse_time(d["time"]) for d in ss.drinks])
        ss.drinks = [d for _, d in sorted(zip(offs, ss.drinks), key=lambda p: p[0])]


# =========================
# Callbacks
# =========================
def _editor_key() -> str:
    return f"drinks_editor_{ss.editor_ver}"


def add_drink(key: str):
    now = _now()
    now = now.replace(minute=now.minute - now.minute % 5)
    d = DRINKS[key]
    ss.drinks = ss.drinks + [{"time": _fmt_time(now.time()), "drink": key, "ml": float(d["ml"]), "abv": round(d["abv"] * 100, 1)}]
    _sort_drinks()
    ss.editor_ver += 1


def clear_drinks():
    ss.drinks = []
    ss.editor_ver += 1


def apply_editor_changes():
    changes = ss[_editor_key()]
    rows = [dict(d) for d in ss.drinks]
    for idx, edit in changes.get("edited_rows", {}).items():
        row = rows[int(idx)]
        if "drink" in edit and edit["drink"] in DRINKS and edit["drink"] != row["drink"]:
            row["drink"] = edit["drink"]
            row["ml"] = float(DRINKS[edit["drink"]]["ml"])
            row["abv"] = round(DRINKS[edit["drink"]]["abv"] * 100, 1)
        if edit.get("time"):
            row["time"] = _fmt_time(_parse_time(edit["time"]))
        if edit.get("ml") is not None:
            row["ml"] = float(edit["ml"])
        if edit.get("abv") is not None:
            row["abv"] = float(edit["abv"])
    deleted = set(changes.get("deleted_rows", []))
    rows = [r for i, r in enumerate(rows) if i not in deleted]
    for new in changes.get("added_rows", []):
        key = new.get("drink") if new.get("drink") in DRINKS else "cana"
        d = DRINKS[key]
        time_ = new.get("time") or (rows[-1]["time"] if rows else _fmt_time(_now().time()))
        rows.append({
            "time": _fmt_time(_parse_time(time_)),
            "drink": key,
            "ml": float(new.get("ml") or d["ml"]),
            "abv": float(new.get("abv") or round(d["abv"] * 100, 1)),
        })
    ss.drinks = [r for r in rows if r["ml"] > 0 and 0 < r["abv"] <= 100]
    _sort_drinks()
    ss.editor_ver += 1


def reset_advanced():
    for k, v in ADVANCED_DEFAULTS.items():
        ss[f"adv_{k}"] = v


def forget_me():
    _set_defaults(force=True)
    ss.lang = _browser_lang()
    ss.editor_ver += 1
    ss._forget = True


# =========================
# Header + language
# =========================
head_l, head_r = st.columns([5, 1], vertical_alignment="bottom")
with head_l:
    st.title(t("title"))
with head_r:
    st.selectbox(t("language"), list(LANGUAGES), key="lang", format_func=LANGUAGES.get, label_visibility="collapsed")
st.caption(t("subtitle"))

# =========================
# 1. About you
# =========================
st.subheader(t("you"))
c1, c2, c3, c4 = st.columns(4)
c1.selectbox(t("sex"), ["male", "female"], key="sex", format_func=lambda s: t(f"sex_{s}"))
c2.number_input(t("age"), 18, 100, key="age_years", step=1)
c3.number_input(t("weight"), 35, 200, key="weight_kg", step=1)
c4.number_input(t("height"), 130, 220, key="height_cm", step=1)

# =========================
# 2. Drinks
# =========================
st.subheader(t("drinks"))
st.caption(t("drinks_hint"))
for col, key in zip(st.columns(len(QUICK_DRINKS)), QUICK_DRINKS):
    col.button(
        f"{DRINKS[key]['emoji']} {t(f'drink_{key}')}",
        key=f"add_{key}",
        help=t(f"drink_{key}_desc"),
        on_click=add_drink,
        args=(key,),
        width="stretch",
    )

drinks_df = pd.DataFrame(
    {
        "time": pd.Series([_parse_time(d["time"]) for d in ss.drinks], dtype="object"),
        "drink": pd.Series([d["drink"] for d in ss.drinks], dtype="object"),
        "ml": pd.Series([d["ml"] for d in ss.drinks], dtype="float64"),
        "abv": pd.Series([d["abv"] for d in ss.drinks], dtype="float64"),
    }
)
st.data_editor(
    drinks_df,
    key=_editor_key(),
    on_change=apply_editor_changes,
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    column_config={
        "time": st.column_config.TimeColumn(t("col_time"), format="HH:mm", step=60, required=True),
        "drink": st.column_config.SelectboxColumn(
            t("col_drink"),
            options=list(DRINKS),
            format_func=lambda k: f"{DRINKS[k]['emoji']} {t(f'drink_{k}')}",
            required=True,
            default="cana",
        ),
        "ml": st.column_config.NumberColumn(t("col_ml"), min_value=1, max_value=3000, step=5, help=t("col_ml_help")),
        "abv": st.column_config.NumberColumn(t("col_abv"), min_value=0.5, max_value=96, step=0.5, format="%.1f %%"),
    },
)
if ss.drinks:
    st.button(t("clear_drinks"), on_click=clear_drinks, type="tertiary")

# =========================
# 3. Food
# =========================
st.subheader(t("food"))
st.radio(t("food"), list(FOOD_FACTORS), key="food", format_func=lambda k: t(f"food_{k}"), horizontal=True, label_visibility="collapsed")

# =========================
# 4. Result
# =========================
st.subheader(t("results"))
st.selectbox(t("limit"), ["general", "novice", "custom"], key="limit_profile", format_func=lambda k: t(f"limit_{k}"))
if ss.limit_profile == "custom":
    lc1, lc2 = st.columns(2)
    lc1.number_input(t("limit_brac"), 0.0, 1.5, key="limit_brac", step=0.01, format="%.2f")
    lc2.number_input(t("limit_bac"), 0.0, 3.0, key="limit_bac", step=0.05, format="%.2f")
    limit_brac, limit_bac = ss.limit_brac, ss.limit_bac
else:
    limit_brac, limit_bac = LIMITS[ss.limit_profile]

result_box = st.container()

# =========================
# 5. Advanced options (hidden at the bottom)
# =========================
with st.expander(t("advanced"), expanded=False):
    st.caption(t("advanced_intro"))
    a1, a2 = st.columns(2)
    a1.slider(t("tolerance"), 0.0, 1.0, key="adv_habitual_level", step=0.05, help=t("tolerance_help"))
    a2.slider(t("carbonation"), 0.7, 1.5, key="adv_carbonation_factor", step=0.05)
    a1.slider(t("breath_temp"), 31.0, 37.0, key="adv_breath_temp_c", step=0.1)
    a2.slider(t("dt"), 0.001, 0.01, key="adv_dt_h", step=0.0005, format="%.4f", help=t("dt_help"))
    a1.radio(t("vd_method"), ["watson", "fixed_r"], key="adv_vd_method", format_func=lambda k: t(f"vd_{k}"))
    a2.slider(t("r_widmark"), 0.45, 0.80, key="adv_r_widmark", step=0.01, disabled=ss.adv_vd_method != "fixed_r")

    st.markdown(t("absorption"))
    st.number_input(t("ka"), 0.1, 8.0, key="adv_ka_h", step=0.1)

    st.markdown(t("elimination"))
    st.radio(t("elim_mode"), ["mm", "zero", "ke"], key="adv_elimination_mode", format_func=lambda k: t(f"elim_{k}"), horizontal=True)
    e1, e2, e3, e4 = st.columns(4)
    e1.number_input(t("vmax"), 0.05, 0.60, key="adv_Vmax_g_per_L_h", step=0.01)
    e2.number_input(t("km"), 0.02, 0.60, key="adv_Km_g_per_L", step=0.01)
    e3.number_input(t("beta"), 0.05, 0.60, key="adv_beta_g_per_L_h", step=0.01)
    e4.number_input(t("ke"), 0.05, 0.60, key="adv_ke_h", step=0.01)

    st.markdown(t("bbr"))
    b1, b2 = st.columns(2)
    b1.number_input(t("bbr_base"), 1500.0, 3000.0, key="adv_BBR_base", step=50.0)
    b2.number_input(t("bbr_coeff"), -0.20, 0.20, key="adv_bbr_temp_coeff_per_deg", step=0.005, format="%.3f")

    st.button(t("reset_advanced"), on_click=reset_advanced)

    st.markdown(t("drinks_table"))
    st.dataframe(
        pd.DataFrame(
            {
                t("tbl_drink"): [f"{d['emoji']} {t(f'drink_{k}')}" for k, d in DRINKS.items()],
                t("tbl_ml"): [d["ml"] for d in DRINKS.values()],
                t("tbl_abv"): [f"{d['abv'] * 100:g} %" for d in DRINKS.values()],
                t("tbl_gas"): [t("yes") if d["carbonated"] else t("no") for d in DRINKS.values()],
            }
        ),
        hide_index=True,
        width="stretch",
    )

with st.expander(t("notes")):
    st.markdown(t("notes_body"))

foot_l, foot_r = st.columns([3, 1], vertical_alignment="center")
foot_l.caption(t("privacy"))
foot_r.button(t("forget"), on_click=forget_me, type="secondary")

# =========================
# Simulation + results (rendered into the result container above)
# =========================
@st.cache_data(show_spinner=False, max_entries=64)
def run_simulation(subject_kw: tuple, options_kw: tuple, doses: tuple, duration_h: float, dt_h: float):
    times, bac, brac = simulate_brac(
        subject=Subject(**dict(subject_kw)),
        doses=[(t_, ml, "custom", {"abv": abv, "ka_scale": ks}) for t_, ml, abv, ks in doses],
        opts=ModelOptions(**dict(options_kw)),
        duration_h=duration_h,
        dt_h=dt_h,
    )
    return times, bac, brac


with result_box:
    if not ss.drinks:
        st.info(t("add_drinks_first"))
    else:
        offsets, start_time = _offsets_hours([_parse_time(d["time"]) for d in ss.drinks])
        now = _now()
        start_dt = dt.datetime.combine(now.date(), start_time)
        if start_dt > now + dt.timedelta(hours=6):
            start_dt -= dt.timedelta(days=1)

        doses = tuple(
            (off, float(d["ml"]), float(d["abv"]) / 100.0, ss.adv_carbonation_factor if DRINKS[d["drink"]]["carbonated"] else 1.0)
            for off, d in zip(offsets, ss.drinks)
        )
        subject_kw = (
            ("weight_kg", float(ss.weight_kg)),
            ("height_cm", float(ss.height_cm)),
            ("age_years", float(ss.age_years)),
            ("sex", ss.sex),
            ("breath_temp_c", ss.adv_breath_temp_c),
            ("habitual_level", ss.adv_habitual_level),
            ("vd_method", ss.adv_vd_method),
            ("r_widmark", ss.adv_r_widmark),
        )
        options_kw = (
            ("ka_h", ss.adv_ka_h),
            ("food_factor", FOOD_FACTORS[ss.food]),
            ("carbonation_factor", 1.0),  # applied per drink above
            ("elimination_mode", ss.adv_elimination_mode),
            ("Vmax_g_per_L_h", ss.adv_Vmax_g_per_L_h),
            ("Km_g_per_L", ss.adv_Km_g_per_L),
            ("beta_g_per_L_h", ss.adv_beta_g_per_L_h),
            ("ke_h", ss.adv_ke_h),
            ("BBR_base", ss.adv_BBR_base),
            ("bbr_temp_coeff_per_deg", ss.adv_bbr_temp_coeff_per_deg),
        )
        last_dose_h = max(offsets)
        duration_h = last_dose_h + 24.0
        times, BAC, BrAC = run_simulation(subject_kw, options_kw, doses, duration_h, ss.adv_dt_h)

        # Trim the flat tail once alcohol is gone
        present = np.nonzero(BAC > 1e-4)[0]
        end_idx = len(times) if len(present) == 0 else min(len(times), present[-1] + int(0.5 / ss.adv_dt_h))
        end_idx = max(end_idx, int(np.searchsorted(times, last_dose_h + 1.0)))
        times, BAC, BrAC = times[:end_idx], BAC[:end_idx], BrAC[:end_idx]
        clock = [start_dt + dt.timedelta(hours=float(h)) for h in times]

        # Same night without the last drink (latest by time; drinks are kept sorted)
        skip_idx = len(ss.drinks) - 1
        if len(doses) > 1:
            _, BAC_alt, BrAC_alt = run_simulation(subject_kw, options_kw, doses[:skip_idx], duration_h, ss.adv_dt_h)
            BAC_alt, BrAC_alt = BAC_alt[:end_idx], BrAC_alt[:end_idx]
        else:
            BAC_alt, BrAC_alt = np.zeros_like(BAC), np.zeros_like(BrAC)

        def _summary(brac, bac):
            """Peak index and the moment the curve is back under both limits."""
            idx = int(np.argmax(brac))
            over = np.nonzero((brac > limit_brac) | (bac > limit_bac))[0]
            if len(over) == 0:
                return idx, "never", None
            if over[-1] >= len(times) - 1:
                return idx, "later", None
            return idx, "at", clock[over[-1] + 1]

        def _fmt_dt(value: dt.datetime) -> str:
            day = "" if value.date() == now.date() else f" ({value:%d/%m})"
            return f"{value:%H:%M}{day}"

        def _fmt_span(delta: dt.timedelta) -> str:
            mins = int(round(delta.total_seconds() / 60))
            h, m = divmod(mins, 60)
            return f"{h} h {m:02d} min" if h else f"{m} min"

        idx_max, below_kind, below_at = _summary(BrAC, BAC)
        if below_kind == "never":
            below_text = t("m_below_never")
            status = ("success", t("status_never"))
        elif below_kind == "later":
            below_text = t("m_below_later")
            status = ("error", t("status_over", time=below_text))
        else:
            below_text = _fmt_dt(below_at)
            status = ("warning", t("status_over", time=below_text))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(t("m_peak"), f"{BrAC[idx_max]:.2f} mg/L", help=t("m_peak_help"))
        m2.metric(t("m_peak_time"), f"{clock[idx_max]:%H:%M}")
        m3.metric(t("m_bac"), f"{BAC[idx_max]:.2f} g/L")
        m4.metric(t("m_below"), below_text)
        getattr(st, status[0])(status[1])

        def _chart(y, y_alt, limit, title, y_label, color):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=clock, y=y, mode="lines", line=dict(color=color, width=3), name=t("chart_all"),
                                     hovertemplate="%{x|%H:%M} · %{y:.3f}<extra></extra>"))
            fig.add_trace(go.Scatter(x=clock, y=y_alt, mode="lines", line=dict(color="#94a3b8", width=2, dash="dash"),
                                     name=t("chart_without_last"), hovertemplate="%{x|%H:%M} · %{y:.3f}<extra></extra>"))
            fig.add_hline(y=limit, line_dash="dash", line_color="#dc2626",
                          annotation_text=t("chart_limit", v=f"{limit:.2f}"), annotation_position="top left")
            drink_x = [start_dt + dt.timedelta(hours=off) for off in offsets]
            fig.add_trace(go.Scatter(
                x=drink_x, y=[0] * len(drink_x), mode="text",
                text=[DRINKS[d["drink"]]["emoji"] for d in ss.drinks], textfont=dict(size=18),
                hovertext=[f"{d['time']} · {t('drink_' + d['drink'])}" for d in ss.drinks], hoverinfo="text",
                showlegend=False,
            ))
            if clock[0] <= now <= clock[-1]:
                fig.add_shape(type="line", x0=now, x1=now, y0=0, y1=1, yref="paper", line=dict(color="#64748b", dash="dot"))
                fig.add_annotation(x=now, y=1, yref="paper", text=t("chart_now"), showarrow=False, yanchor="bottom")
            fig.update_layout(title=title, xaxis_title=t("chart_x"), yaxis_title=y_label,
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                              margin=dict(l=10, r=10, t=60, b=10), height=400, hovermode="x unified")
            fig.update_xaxes(tickformat="%H:%M")
            fig.update_yaxes(rangemode="tozero")
            return fig

        st.plotly_chart(_chart(BrAC, BrAC_alt, limit_brac, t("chart_title"), t("chart_y"), "#0f766e"), width="stretch")
        if st.toggle(t("show_bac"), key="show_bac"):
            st.plotly_chart(_chart(BAC, BAC_alt, limit_bac, t("chart_title_bac"), t("chart_y_bac"), "#7c3aed"), width="stretch")

        # ---- What if you skip the last drink? ----
        last = ss.drinks[skip_idx]
        st.markdown(f"#### {t('whatif_title')}")
        st.caption(t("whatif_caption", drink=f"{DRINKS[last['drink']]['emoji']} {t('drink_' + last['drink'])}", time=last["time"]))
        if len(doses) == 1:
            st.success(t("whatif_only_one"))
        else:
            alt_idx, alt_kind, alt_at = _summary(BrAC_alt, BAC_alt)
            if alt_kind == "never":
                alt_below = t("m_below_never")
            elif alt_kind == "later":
                alt_below = t("m_below_later")
            else:
                alt_below = _fmt_dt(alt_at)
            w1, w2, w3 = st.columns(3)
            w1.metric(t("m_peak"), f"{BrAC_alt[alt_idx]:.2f} mg/L",
                      delta=f"{BrAC_alt[alt_idx] - BrAC[idx_max]:+.2f} mg/L", delta_color="inverse")
            w2.metric(t("m_bac"), f"{BAC_alt[alt_idx]:.2f} g/L",
                      delta=f"{BAC_alt[alt_idx] - BAC[idx_max]:+.2f} g/L", delta_color="inverse")
            w3.metric(t("m_below"), alt_below)
            if below_kind != "never" and alt_kind == "never":
                st.success(t("whatif_never"))
            elif below_kind == "at" and alt_kind == "at" and alt_at < below_at:
                st.info(t("whatif_earlier", time=alt_below, span=_fmt_span(below_at - alt_at)))
            elif below_kind == "later" and alt_kind == "at":
                st.info(t("whatif_at", time=alt_below))
            elif below_kind == "never":
                st.success(t("whatif_both_ok"))
            else:
                st.warning(t("whatif_same"))

        out_df = pd.DataFrame({"time": [c.strftime("%Y-%m-%d %H:%M:%S") for c in clock], "t_h": times,
                               "BAC_g_per_L": BAC, "BrAC_mg_per_L": BrAC,
                               "BAC_without_last_g_per_L": BAC_alt, "BrAC_without_last_mg_per_L": BrAC_alt})
        st.download_button(t("export"), data=out_df.to_csv(index=False).encode("utf-8"),
                           file_name="brac_bac_simulation.csv", mime="text/csv")

# =========================
# Remember everything in the browser
# =========================
if ss.pop("_forget", False):
    storage.clear(STORAGE_KEY)
    ss._forgotten_payload = _payload()
    st.toast(t("forgotten"))
elif ss.get("_forgotten_payload") == _payload():
    pass  # nothing changed since the user asked to forget: don't save defaults again
else:
    ss.pop("_forgotten_payload", None)
    storage.save(STORAGE_KEY, _payload())
