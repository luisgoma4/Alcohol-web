"""Remember the user's data in the browser's localStorage.

Nothing is stored on the server: a tiny Streamlit component reads the saved
JSON once when the page loads and writes it again whenever it changes.
"""

import json

import streamlit as st

_JS = """
export default function (component) {
  const { data, setStateValue } = component;
  if (!data) return;
  try {
    if (data.save && data.save === window.__bracLastSaved) return;
    if (data.clear) {
      window.localStorage.removeItem(data.key);
      window.__bracLastSaved = null;
    } else if (data.save) {
      window.localStorage.setItem(data.key, data.save);
      window.__bracLastSaved = data.save;
    }
    if (data.load) {
      setStateValue("loaded", window.localStorage.getItem(data.key) ?? "");
    }
  } catch (e) {
    // Storage blocked (private mode, disabled cookies...): keep working without it.
    if (data.load) setStateValue("loaded", "");
  }
}
"""

_component = st.components.v2.component("brac_local_storage", js=_JS)


def load(storage_key: str) -> dict | None:
    """Read the saved data. Call at the top of the script, before any widget.

    Returns the stored dict once, on the run where it arrives from the browser
    (an empty dict if nothing was saved), and None on every other run.
    """
    ss = st.session_state
    ss.setdefault("_storage_hydrated", False)
    if ss._storage_hydrated:
        return None

    result = _component(
        key="brac_storage_load",
        data={"key": storage_key, "load": True},
        default={"loaded": None},
        on_loaded_change=lambda: None,
        height=0,
    )
    raw = getattr(result, "loaded", None)
    if raw is None:
        return None

    ss._storage_hydrated = True
    try:
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data


def is_ready() -> bool:
    """True once the saved data has been read (so saving won't overwrite it)."""
    return bool(st.session_state.get("_storage_hydrated"))


def save(storage_key: str, payload: dict) -> None:
    """Write payload to the browser if it changed. Call at the end of the script."""
    ss = st.session_state
    if not is_ready():
        return  # never overwrite saved data with defaults before it was read
    text = json.dumps(payload, sort_keys=True)
    # Mounted on every run with a stable key; the browser only writes when the text changes.
    _component(key="brac_storage_save", data={"key": storage_key, "save": text}, height=0)


def clear(storage_key: str) -> None:
    """Delete the saved data from the browser."""
    ss = st.session_state
    ss._storage_hydrated = True
    ss._storage_seq = ss.get("_storage_seq", 0) + 1
    _component(
        key=f"brac_storage_clear_{ss._storage_seq}",
        data={"key": storage_key, "clear": True},
        height=0,
    )
