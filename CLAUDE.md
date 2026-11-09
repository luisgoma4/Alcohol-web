# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Streamlit app that estimates breath and blood alcohol over time from a pharmacokinetic model, built as a phone-style app. The repo is public. Changes go through a branch and PR.

## Commands

```bash
# Run locally (shared workspace environment; never create a venv in this folder)
~/.venvs/comun/bin/python -m streamlit run streamlit_app.py --server.headless true --server.port 8599

# Run in Docker (port 8501)
docker compose up --build

# Run the model on its own (example at the bottom of the file)
~/.venvs/comun/bin/python alcohol_test3.py
```

There are no tests, linter or CI. `AppTest` stops at the storage gate described below and never draws a screen, so UI changes must be checked in a real browser.

## Architecture

- `alcohol_test3.py`: the model. `simulate_brac` integrates a GI-to-central compartment model with Euler steps and Michaelis-Menten, zero-order or first-order elimination. It has no Streamlit dependency.
- `streamlit_app.py`: all UI and state, top to bottom in one script.
- `config.py`: drinks, food factors and defaults. `DEFAULTS` holds profile values; `ADVANCED_DEFAULTS` holds model values, exposed as `adv_<name>` in session state.
- `i18n.py`: `TEXTS["es"]` and `TEXTS["en"]`. Every string must exist in both.
- `storage.py`: Streamlit component that keeps the data in the browser's `localStorage`. Nothing is stored on the server.

Script order on each rerun matters: set defaults, load saved data, `st.stop()` until the browser has answered, `st.set_page_config`, compute the result (before drawing, because every screen shows it), draw the four screens (`SCREENS`), save.

`run_simulation` is cached, so it takes hashable tuples. Carbonation is applied per drink, which is why the global `carbonation_factor` is passed as 1.0.

## Things that break easily

- **Saved data:** `_apply_saved` only accepts keys listed in `VALID`, so a new persisted field needs an entry there. Advanced values are saved only when they differ from the default, so changing a default in `ADVANCED_DEFAULTS` also changes it for everyone who never customized it.
- **Dockerfile:** it copies files by name. A new module must be added to its `COPY` line.
- **Streamlit internals:** `style.css` and `_SWIPE_JS` target `data-testid`, `data-baseweb` and `.st-key-*` selectors, so a Streamlit upgrade can silently break them. The app has only been verified on 1.67, although `requirements.txt` allows >=1.52.
- **Number fields:** `_SWIPE_JS` also sets the mobile keyboard type and clamps out-of-range or empty values, working around Streamlit's own behavior. Swipe is skipped when a touch starts on an input.

## Layout constraint

Each screen must fit the visible height with no page scroll, above the fixed bottom navigation. Heights are based on `100dvh - var(--nav)`, with a compact mode under 700 px of height. Variable-length content (drink list, Advanced sections) scrolls inside its own box. Profile and Advanced have nothing that grows on its own, so they use `min-height` and spread their content, with control sizes that follow the screen height (`--ctl`). Page scroll is accepted only at 360x640 with the custom limit selected or all Advanced sections open, and while the on-screen keyboard is open.

After a layout change, measure `scrollHeight` against `clientHeight` on `[data-testid="stMain"]` at 360x640, 390x844 and 1440x900, in both languages, with 0, 3 and 8 drinks, and look at the screenshots.

## Model

The app informs a decision about driving. Keep the disclaimers visible, and don't make a result look safer or more precise than it is.

- `habitual_level` defaults to 0 on purpose: 0.5 raised maximum elimination by 30 % for everyone and brought the "under the limit" time forward.
- Known open issue: with `vd_method="watson"`, total body water is used directly as the distribution volume, without the blood water factor (~0.8). This can overestimate alcohol by about 25 %. Fixing it lowers every result, so review it against the references first.
- "Now" rounds down to 5 minutes, so the estimated time can come out up to 4 minutes early.
