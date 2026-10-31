import datetime as dt
from html import escape
from pathlib import Path
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
        ss.pop("_undo_drinks", None)
    ss.setdefault("next_drink_id", 0)
    ss.setdefault("add_when", "now")


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


def _new_drink(key: str, time_text: str, ml: float | None = None, abv: float | None = None) -> dict:
    """A drink entry with a unique id (used to key its edit widgets)."""
    ss.next_drink_id = ss.get("next_drink_id", 0) + 1
    d = DRINKS[key]
    return {
        "id": ss.next_drink_id,
        "rev": 0,  # bumped on every edit so the edit widgets restart from the new values
        "time": time_text,
        "drink": key,
        "ml": float(d["ml"] if ml is None else ml),
        "abv": float(round(d["abv"] * 100, 1) if abv is None else abv),
    }


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
                drinks.append(_new_drink(d["drink"], d["time"], float(d["ml"]), float(d["abv"])))
        except (KeyError, TypeError, ValueError):
            continue
    ss.drinks = drinks


def _payload() -> dict:
    data = {k: ss[k] for k in DEFAULTS}
    if ss.limit_profile != "custom":
        data.pop("limit_brac")
        data.pop("limit_bac")
    data["drinks"] = [{k: d[k] for k in ("time", "drink", "ml", "abv")} for d in ss.drinks]
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

st.set_page_config(page_title=t("page_title"), page_icon="🍺", layout="centered", initial_sidebar_state="collapsed")


def _sort_drinks():
    if ss.drinks:
        offs, _ = _offsets_hours([_parse_time(d["time"]) for d in ss.drinks])
        ss.drinks = [d for _, d in sorted(zip(offs, ss.drinks), key=lambda p: p[0])]


# =========================
# Callbacks
# =========================
def _round5(value: dt.datetime) -> dt.datetime:
    return value.replace(minute=value.minute - value.minute % 5)


def _add_time() -> str:
    """Time for a new drink: now, or the time the user picked."""
    if ss.add_when == "custom" and ss.get("add_time"):
        return _fmt_time(_parse_time(ss.add_time))
    return _fmt_time(_round5(_now()).time())


def add_drink(key: str, ml: float | None = None, abv: float | None = None):
    new = _new_drink(key, _add_time(), ml, abv)
    ss.drinks = ss.drinks + [new]
    ss.pop("_undo_drinks", None)
    _sort_drinks()
    ss._toast = ("added", new)


def repeat_drink(drink_id: int):
    d = next(x for x in ss.drinks if x["id"] == drink_id)
    add_drink(d["drink"], d["ml"], d["abv"])


def remove_drink(drink_id: int):
    ss._undo_drinks = list(ss.drinks)
    ss.drinks = [d for d in ss.drinks if d["id"] != drink_id]


def clear_drinks():
    ss._undo_drinks = list(ss.drinks)
    ss.drinks = []


def undo_remove():
    ss.drinks = ss.pop("_undo_drinks", ss.drinks)


def _edit_key(d: dict, field: str) -> str:
    return f"ed_{d['id']}_{d['rev']}_{field}"


def edit_drink(drink_id: int, field: str):
    for d in ss.drinks:
        value = ss.get(_edit_key(d, field)) if d["id"] == drink_id else None
        if value is None:
            continue
        d["rev"] += 1
        if field == "drink" and value != d["drink"]:
            # New drink type: start from its standard amount and strength
            d.update(drink=value, ml=float(DRINKS[value]["ml"]), abv=float(round(DRINKS[value]["abv"] * 100, 1)))
        elif field == "time":
            d["time"] = _fmt_time(_parse_time(value))
        elif field in ("ml", "abv"):
            d[field] = float(value)
    ss.drinks = list(ss.drinks)
    _sort_drinks()


def reset_advanced():
    for k, v in ADVANCED_DEFAULTS.items():
        ss[f"adv_{k}"] = v


def forget_me():
    _set_defaults(force=True)
    ss.lang = _browser_lang()
    ss._forget = True


# =========================
# Screens ("reel"): profile · drinks · prediction · advanced
# =========================
SCREENS = ["profile", "drinks", "result", "advanced"]


def _screen_labels(lang: str) -> list[str]:
    tr = translator(lang)
    return [tr(f"nav_{k}") for k in SCREENS]


def _on_screen_change():
    labels = _screen_labels(ss.lang)
    if ss.get("screen") in labels:
        ss.screen_idx = labels.index(ss.screen)


def go_to(idx: int):
    ss.screen_idx = idx
    ss.screen = _screen_labels(ss.lang)[idx]


def _on_lang_change():
    ss.screen = _screen_labels(ss.lang)[ss.get("screen_idx", 0)]


def _grams(d: dict) -> float:
    return d["ml"] * d["abv"] / 100.0 * 0.789


def _drink_name(key: str) -> str:
    return t(f"drink_{key}")


def _drink_label(key: str) -> str:
    return f"{DRINKS[key]['emoji']} {_drink_name(key)}"


def _hero(kind: str, step: int, emoji: str, title: str, sub: str = "", badge: str = "", big: str = ""):
    st.html(
        f'<div class="hero hero-{kind}">'
        f'<div class="step">{step} / 4</div>'
        f'<div class="emoji">{emoji}</div>'
        f'<div class="title">{escape(title)}</div>'
        + (f'<div class="big">{escape(big)}</div>' if big else "")
        + (f'<div class="sub">{escape(sub)}</div>' if sub else "")
        + (f'<div class="badge">{escape(badge)}</div>' if badge else "")
        + "</div>"
    )


def _label(text: str):
    st.html(f'<div class="label">{escape(text)}</div>')


def _next_button(idx: int):
    st.button(t("next", screen=_screen_labels(ss.lang)[idx].replace("\n", " ")), type="primary",
              width="stretch", on_click=go_to, args=(idx,), key=f"next_{idx}")


# Swipe left/right between screens on touch devices (plus scroll to top on change)
_SWIPE_JS = """
export default function () {
  if (window.__bracSwipe) return;
  window.__bracSwipe = true;
  const toTop = () => {
    window.scrollTo({ top: 0 });
    document.querySelector('[data-testid="stMain"]')?.scrollTo({ top: 0 });
  };
  let x0 = null, y0 = null, skip = false;
  document.addEventListener('touchstart', (e) => {
    const p = e.touches[0]; x0 = p.clientX; y0 = p.clientY;
    skip = !!e.target.closest('[data-baseweb="slider"], input, textarea, [data-baseweb="popover"], .js-plotly-plot, [data-testid="stDataFrame"]');
  }, { passive: true });
  document.addEventListener('touchend', (e) => {
    if (x0 === null || skip) { x0 = null; return; }
    const p = e.changedTouches[0]; const dx = p.clientX - x0, dy = p.clientY - y0; x0 = null;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
    const tabs = [...document.querySelectorAll('.st-key-screen [role="tab"]')];
    const i = tabs.findIndex((b) => b.getAttribute('aria-selected') === 'true');
    const j = dx < 0 ? i + 1 : i - 1;
    if (j >= 0 && j < tabs.length) { tabs[j].click(); toTop(); }
  }, { passive: true });
  document.addEventListener('click', (e) => {
    if (e.target.closest('[role="tab"]') || e.target.closest('[class*="st-key-next_"]')) setTimeout(toTop, 50);
  });
}
"""
_swipe = st.components.v2.component("brac_swipe", js=_SWIPE_JS, isolate_styles=False)


# =========================
# Simulation (runs before drawing so every screen can show the result)
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


def _limits() -> tuple[float, float]:
    if ss.limit_profile == "custom":
        return float(ss.limit_brac), float(ss.limit_bac)
    return LIMITS[ss.limit_profile]


def compute_result() -> dict | None:
    if not ss.drinks:
        return None
    limit_brac, limit_bac = _limits()
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
    if len(doses) > 1:
        _, BAC_alt, BrAC_alt = run_simulation(subject_kw, options_kw, doses[:-1], duration_h, ss.adv_dt_h)
        BAC_alt, BrAC_alt = BAC_alt[:end_idx], BrAC_alt[:end_idx]
    else:
        BAC_alt, BrAC_alt = np.zeros_like(BAC), np.zeros_like(BrAC)

    def summary(brac, bac):
        idx = int(np.argmax(brac))
        over = np.nonzero((brac > limit_brac) | (bac > limit_bac))[0]
        if len(over) == 0:
            return {"idx": idx, "kind": "never", "at": None}
        if over[-1] >= len(times) - 1:
            return {"idx": idx, "kind": "later", "at": None}
        return {"idx": idx, "kind": "at", "at": clock[over[-1] + 1]}

    return {
        "now": now, "start_dt": start_dt, "offsets": offsets, "times": times, "clock": clock,
        "BAC": BAC, "BrAC": BrAC, "BAC_alt": BAC_alt, "BrAC_alt": BrAC_alt,
        "main": summary(BrAC, BAC), "alt": summary(BrAC_alt, BAC_alt),
        "limit_brac": limit_brac, "limit_bac": limit_bac,
    }


def _fmt_dt(value: dt.datetime, now: dt.datetime) -> str:
    day = "" if value.date() == now.date() else f" ({value:%d/%m})"
    return f"{value:%H:%M}{day}"


def _fmt_span(delta: dt.timedelta) -> str:
    mins = int(round(delta.total_seconds() / 60))
    h, m = divmod(mins, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _below_text(s: dict, now: dt.datetime) -> str:
    if s["kind"] == "never":
        return t("m_below_never")
    if s["kind"] == "later":
        return t("m_below_later")
    return _fmt_dt(s["at"], now)


res = compute_result()

# =========================
# Layout
# =========================
with open(Path(__file__).with_name("style.css"), encoding="utf-8") as fh:
    st.html(f"<style>{fh.read()}</style>")
with st.container(key="swipe"):
    _swipe(key="swipe_js", height=0)

ss.setdefault("screen_idx", 0)
labels = _screen_labels(ss.lang)
tab_profile, tab_drinks, tab_result, tab_adv = st.tabs(
    labels, key="screen", default=labels[ss.screen_idx], on_change=_on_screen_change
)

if "_toast" in ss:
    _, new = ss.pop("_toast")
    st.toast(t("added_toast", drink=_drink_label(new["drink"]), time=new["time"]), icon="✅")

# ---------- 1 · Profile ----------
with tab_profile:
    _hero("profile", 1, "👤", t("profile_title"), t("profile_sub"))
    with st.container(key="card_lang"):
        _label(t("language"))
        st.segmented_control(t("language"), list(LANGUAGES), key="lang", format_func=LANGUAGES.get, required=True,
                             label_visibility="collapsed", width="stretch", on_change=_on_lang_change)
    with st.container(key="card_profile"):
        _label(t("sex"))
        st.segmented_control(t("sex"), ["male", "female"], key="sex", format_func=lambda s: t(f"sex_{s}"),
                             required=True, label_visibility="collapsed", width="stretch")
        for key, lo, hi, unit in (("age_years", 18, 100, t("unit_years")), ("weight_kg", 35, 200, "kg"), ("height_cm", 130, 220, "cm")):
            st.html(f'<div class="value-pill"><span>{escape(t(key))}</span><span>{ss[key]} {unit}</span></div>')
            st.slider(t(key), lo, hi, key=key, step=1, label_visibility="collapsed")
    _next_button(1)

# ---------- 2 · Drinks ----------
with tab_drinks:
    if res is None:
        badge = t("badge_empty")
    elif res["main"]["kind"] == "never":
        badge = t("badge_ok")
    else:
        badge = t("badge_over", time=_below_text(res["main"], res["now"]))
    _hero("drinks", 2, "🍺", t("drinks_title"), badge=badge)

    with st.container(key="card_add"):
        _label(t("add_when"))
        st.segmented_control(t("add_when"), ["now", "custom"], key="add_when", required=True,
                             format_func=lambda k: t(f"add_when_{k}"), label_visibility="collapsed", width="stretch")
        if ss.add_when == "custom":
            st.time_input(t("add_time"), value=ss.get("add_time") or _round5(_now()).time(), key="add_time", step=300,
                          label_visibility="collapsed")
        _label(t("add_tap"))
        with st.container(key="add_buttons"):
            for key in QUICK_DRINKS:
                d = DRINKS[key]
                st.button(f"{_drink_name(key)} *{d['ml']} ml*", icon=d["emoji"], key=f"add_{key}",
                          on_click=add_drink, args=(key,))

    with st.container(key="card_food"):
        _label(t("food"))
        st.segmented_control(t("food"), list(FOOD_FACTORS), key="food", format_func=lambda k: t(f"food_{k}"),
                             required=True, label_visibility="collapsed", width="stretch")

    with st.container(key="card_list"):
        if ss.drinks:
            total_g = sum(_grams(d) for d in ss.drinks)
            _label(t("your_drinks", n=len(ss.drinks), g=f"{total_g:.0f}"))
            for d in ss.drinks:
                did = d["id"]
                with st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"drink_card_{did}"):
                    st.html(
                        f'<div class="drink-row"><div class="em">{DRINKS[d["drink"]]["emoji"]}</div><div>'
                        f'<div class="nm">{escape(_drink_name(d["drink"]))}</div>'
                        f'<div class="meta">{d["time"]} · {d["ml"]:g} ml</div></div></div>',
                        width="stretch",
                    )
                    with st.popover("✏️", help=t("edit_help")):
                        st.selectbox(t("col_drink"), list(DRINKS), index=list(DRINKS).index(d["drink"]),
                                     key=_edit_key(d, "drink"), format_func=_drink_label,
                                     on_change=edit_drink, args=(did, "drink"))
                        st.time_input(t("col_time"), value=_parse_time(d["time"]), key=_edit_key(d, "time"), step=300,
                                      on_change=edit_drink, args=(did, "time"))
                        st.number_input(t("col_ml"), 1.0, 3000.0, value=float(d["ml"]), key=_edit_key(d, "ml"), step=5.0,
                                        format="%.0f", help=t("col_ml_help"), on_change=edit_drink, args=(did, "ml"))
                        st.number_input(t("col_abv"), 0.5, 96.0, value=float(d["abv"]), key=_edit_key(d, "abv"), step=0.5,
                                        format="%.1f", on_change=edit_drink, args=(did, "abv"))
                    st.button("➕", key=f"rep_{did}", help=t("repeat_help"), on_click=repeat_drink, args=(did,))
                    st.button("🗑️", key=f"del_{did}", help=t("remove_help"), on_click=remove_drink, args=(did,))
        else:
            st.html(f'<div class="empty"><span class="em">🥤</span>{escape(t("drinks_empty"))}</div>')
        with st.container(horizontal=True, gap="small"):
            if ss.get("_undo_drinks") is not None:
                st.button(t("undo"), on_click=undo_remove)
            if ss.drinks:
                st.button(t("clear_drinks"), on_click=clear_drinks, type="tertiary")
    _next_button(2)

# ---------- 3 · Prediction ----------
with tab_result:
    if res is None:
        _hero("result", 3, "📈", t("result_title"), t("add_drinks_first"))
        st.button(t("go_drinks"), type="primary", width="stretch", on_click=go_to, args=(1,), key="go_drinks")
    else:
        now, clock, main, alt = res["now"], res["clock"], res["main"], res["alt"]
        BrAC, BAC, BrAC_alt, BAC_alt = res["BrAC"], res["BAC"], res["BrAC_alt"], res["BAC_alt"]
        if main["kind"] == "never":
            _hero("ok", 3, "✅", t("result_ok"), t("result_ok_sub"))
        elif main["kind"] == "later":
            _hero("bad", 3, "⛔", t("result_below_at"), t("result_over_sub"), big=t("m_below_later"))
        else:
            _hero("warn", 3, "⏱️", t("result_below_at"), t("result_over_sub"), big=_below_text(main, now))

        i = main["idx"]
        total_g = sum(_grams(d) for d in ss.drinks)
        st.html(
            '<div class="stats">'
            f'<div class="stat"><div class="k">{escape(t("m_peak"))}</div><div class="v">{BrAC[i]:.2f} <small>mg/L</small></div></div>'
            f'<div class="stat"><div class="k">{escape(t("m_peak_time"))}</div><div class="v">{clock[i]:%H:%M}</div></div>'
            f'<div class="stat"><div class="k">{escape(t("m_bac"))}</div><div class="v">{BAC[i]:.2f} <small>g/L</small></div></div>'
            f'<div class="stat"><div class="k">{escape(t("m_total"))}</div><div class="v">{total_g:.0f} <small>g</small></div></div>'
            "</div>"
        )

        show_bac = ss.get("show_bac", False)
        y, y_alt = (BAC, BAC_alt) if show_bac else (BrAC, BrAC_alt)
        limit = res["limit_bac"] if show_bac else res["limit_brac"]
        color = "#7c3aed" if show_bac else "#0d9488"
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=clock, y=y, mode="lines", line=dict(color=color, width=4), name=t("chart_all"),
                                 fill="tozeroy", fillcolor="rgba(13,148,136,.10)" if not show_bac else "rgba(124,58,237,.10)",
                                 hovertemplate="%{x|%H:%M} · %{y:.2f}<extra></extra>"))
        fig.add_trace(go.Scatter(x=clock, y=y_alt, mode="lines", line=dict(color="#94a3b8", width=2, dash="dash"),
                                 name=t("chart_without_last"), hovertemplate="%{x|%H:%M} · %{y:.2f}<extra></extra>"))
        fig.add_hline(y=limit, line_dash="dot", line_color="#dc2626", line_width=2,
                      annotation_text=t("chart_limit", v=f"{limit:.2f}"), annotation_position="top right",
                      annotation_font_color="#dc2626")
        drink_x = [res["start_dt"] + dt.timedelta(hours=off) for off in res["offsets"]]
        fig.add_trace(go.Scatter(x=drink_x, y=[0] * len(drink_x), mode="text",
                                 text=[DRINKS[d["drink"]]["emoji"] for d in ss.drinks], textfont=dict(size=18),
                                 hoverinfo="skip", showlegend=False))
        if clock[0] <= now <= clock[-1]:
            fig.add_shape(type="line", x0=now, x1=now, y0=0, y1=1, yref="paper", line=dict(color="#0f172a", dash="dot", width=1))
            fig.add_annotation(x=now, y=1, yref="paper", text=t("chart_now"), showarrow=False, yanchor="bottom",
                               font=dict(size=11, color="#0f172a"))
        fig.update_layout(height=300, margin=dict(l=4, r=4, t=36, b=4), hovermode="x unified", dragmode=False,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0, font=dict(size=11)))
        fig.update_xaxes(tickformat="%H:%M", fixedrange=True, showgrid=False)
        fig.update_yaxes(rangemode="tozero", fixedrange=True, gridcolor="#e2e8f0",
                         title=dict(text=t("chart_y_bac") if show_bac else t("chart_y"), font=dict(size=11)))
        with st.container(key="card_chart"):
            _label(t("chart_title_bac") if show_bac else t("chart_title"))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "scrollZoom": False, "responsive": True})
            st.toggle(t("show_bac"), key="show_bac")

        # What if you skip the last drink?
        last = ss.drinks[-1]
        if len(ss.drinks) == 1:
            body, sub = t("whatif_none"), t("whatif_only_one")
        elif alt["kind"] == "never":
            body, sub = t("whatif_ok_big"), t("whatif_never_short")
        else:
            body = _below_text(alt, now)
            if main["kind"] == "at" and alt["kind"] == "at" and alt["at"] < main["at"]:
                sub = t("whatif_earlier_short", span=_fmt_span(main["at"] - alt["at"]))
            else:
                sub = t("whatif_same_short")
        st.html(
            f'<div class="whatif"><div class="t">🤔 {escape(t("whatif_title_short", drink=_drink_label(last["drink"])))}</div>'
            f'<div class="big">{escape(body)}</div><div class="s">{escape(sub)}</div></div>'
        )

        with st.container(key="card_limit"):
            _label(t("limit"))
            st.segmented_control(t("limit"), ["general", "novice", "custom"], key="limit_profile",
                                 format_func=lambda k: t(f"limit_{k}_short"), required=True,
                                 label_visibility="collapsed", width="stretch")
            if ss.limit_profile == "custom":
                lc1, lc2 = st.columns(2)
                lc1.number_input(t("limit_brac"), 0.0, 1.5, key="limit_brac", step=0.01, format="%.2f")
                lc2.number_input(t("limit_bac"), 0.0, 3.0, key="limit_bac", step=0.05, format="%.2f")
            else:
                st.caption(t(f"limit_{ss.limit_profile}"))

        out_df = pd.DataFrame({"time": [c.strftime("%Y-%m-%d %H:%M:%S") for c in clock], "t_h": res["times"],
                               "BAC_g_per_L": BAC, "BrAC_mg_per_L": BrAC,
                               "BAC_without_last_g_per_L": BAC_alt, "BrAC_without_last_mg_per_L": BrAC_alt})
        st.download_button(t("export"), data=out_df.to_csv(index=False).encode("utf-8"), icon="⬇️",
                           file_name="brac_bac_simulation.csv", mime="text/csv", width="stretch")
        st.caption(t("disclaimer"))

# ---------- 4 · Advanced ----------
with tab_adv:
    _hero("advanced", 4, "⚙️", t("advanced_title"), t("advanced_intro"))
    with st.container(key="card_adv_body"):
        _label(t("adv_body"))
        st.slider(t("tolerance"), 0.0, 1.0, key="adv_habitual_level", step=0.05, help=t("tolerance_help"))
        st.slider(t("carbonation"), 0.7, 1.5, key="adv_carbonation_factor", step=0.05)
        st.slider(t("breath_temp"), 31.0, 37.0, key="adv_breath_temp_c", step=0.1)
    with st.container(key="card_adv_model"):
        _label(t("adv_model"))
        st.radio(t("vd_method"), ["watson", "fixed_r"], key="adv_vd_method", format_func=lambda k: t(f"vd_{k}"))
        st.slider(t("r_widmark"), 0.45, 0.80, key="adv_r_widmark", step=0.01, disabled=ss.adv_vd_method != "fixed_r")
        st.number_input(t("ka"), 0.1, 8.0, key="adv_ka_h", step=0.1)
        st.selectbox(t("elim_mode"), ["mm", "zero", "ke"], key="adv_elimination_mode", format_func=lambda k: t(f"elim_{k}"))
        e1, e2 = st.columns(2)
        e1.number_input(t("vmax"), 0.05, 0.60, key="adv_Vmax_g_per_L_h", step=0.01)
        e2.number_input(t("km"), 0.02, 0.60, key="adv_Km_g_per_L", step=0.01)
        e1.number_input(t("beta"), 0.05, 0.60, key="adv_beta_g_per_L_h", step=0.01)
        e2.number_input(t("ke"), 0.05, 0.60, key="adv_ke_h", step=0.01)
        e1.number_input(t("bbr_base"), 1500.0, 3000.0, key="adv_BBR_base", step=50.0)
        e2.number_input(t("bbr_coeff"), -0.20, 0.20, key="adv_bbr_temp_coeff_per_deg", step=0.005, format="%.3f")
        st.slider(t("dt"), 0.001, 0.01, key="adv_dt_h", step=0.0005, format="%.4f", help=t("dt_help"))
        st.button(t("reset_advanced"), on_click=reset_advanced, icon="🔄", width="stretch")
    with st.expander(t("drinks_table")):
        st.dataframe(
            pd.DataFrame(
                {
                    t("tbl_drink"): [_drink_label(k) for k in DRINKS],
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
    with st.container(key="card_privacy"):
        _label(t("privacy_title"))
        st.caption(t("privacy"))
        st.button(t("forget"), on_click=forget_me, width="stretch")


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
