"""Settings - AI providers. Grade with the shared account, or your own key."""
from __future__ import annotations

import streamlit as st

import sys
from pathlib import Path

# Streamlit puts only this file's directory on sys.path - see app.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend_streamlit.components import api_client
from frontend_streamlit.components.ui import page_setup, require_auth

page_setup("AI providers")
require_auth()

st.title("AI providers")

data = api_client.provider_settings()
if data is None:
    st.stop()

by_provider = {c["provider"]: c for c in data["credentials"]}

_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Claude (Anthropic)",
    "local": "Local model (Ollama / vLLM / LM Studio)",
}
_KEY_HELP = {
    "openai": "Starts with `sk-`. Create one at platform.openai.com/api-keys.",
    "anthropic": "Starts with `sk-ant-`. Create one at console.anthropic.com.",
    "local": "Most local servers ignore the key. Leave it blank unless yours needs one.",
}

# ---------------------------------------------------------------------
# Which credentials are grading right now
# ---------------------------------------------------------------------
st.subheader("Which account grades your submissions")

admin_label = _LABELS.get(data["administrator_provider"],
                          data["administrator_provider"])
if data["using_administrator"]:
    if data["administrator_available"]:
        st.success(f"Using the shared account set up by your administrator "
                   f"({admin_label}). You do not need your own key.",
                   icon=":material/verified:")
    else:
        st.warning(
            "You are set to use the administrator's account, but it is not "
            "configured on this server, so grading will fail. Add your own "
            "key below and switch to it.",
            icon=":material/warning:",
        )
else:
    st.info(f"Using **your own** {_LABELS.get(data['preferred_provider'], data['preferred_provider'])} "
            f"key. Your usage is billed to your own account.",
            icon=":material/key:")

options = ["administrator"] + [
    p for p in data["supported"] if p in by_provider
]
labels = {"administrator": f"Administrator's shared account ({admin_label})"}
labels.update({p: f"My own {_LABELS.get(p, p)} key" for p in options[1:]})

current = data["preferred_provider"] or "administrator"
choice = st.radio(
    "Grade using",
    options,
    index=options.index(current) if current in options else 0,
    format_func=lambda p: labels[p],
)
if choice != current and st.button("Switch", type="primary"):
    if api_client.set_provider_preference(
            None if choice == "administrator" else choice):
        st.success("Switched.")
        st.rerun()

st.caption(
    "Saving a key does not switch grading to it - that is this choice, so "
    "pasting a key can never silently redirect a running course's spend."
)

st.divider()

# ---------------------------------------------------------------------
# Manage keys
# ---------------------------------------------------------------------
st.subheader("Your API keys")
st.caption(
    "Keys are encrypted before they are stored, shown only as the last four "
    "characters afterwards, and never written to logs. There is no way to "
    "read one back - if you lose it, replace it."
)

for provider in data["supported"]:
    saved = by_provider.get(provider)
    status = ""
    if saved:
        if saved["last_test_ok"] is True:
            status = "  ·  tested OK"
        elif saved["last_test_ok"] is False:
            status = "  ·  last test failed"
    header = f"{_LABELS.get(provider, provider)}"
    if saved and saved["has_key"]:
        header += f"  —  {saved['masked_key']}{status}"
    elif saved:
        header += f"  —  configured{status}"
    else:
        header += "  —  not set up"

    with st.expander(header, expanded=False):
        # Ollama helper: what can *this server* actually see?
        default_url = (saved or {}).get("base_url") or ""
        if provider == "local":
            st.caption(
                "AutoGrade runs on the server, so it must be able to reach "
                "your Ollama host itself. A model installed only on your own "
                "laptop is not reachable from a hosted AutoGrade unless you "
                "expose it - see RUN_AND_SHARE.md."
            )
            probe_url = st.text_input(
                "Ollama base URL", value=default_url or "http://localhost:11434/v1",
                key=f"probe_{provider}",
                help="Use http://host.docker.internal:11434/v1 when AutoGrade "
                     "runs in Docker on the same machine as Ollama.",
            )
            if st.button("Check this server", key=f"discover_{provider}"):
                found = api_client.discover_local_models(probe_url)
                if found and found.get("reachable"):
                    st.success(found["detail"])
                    if found.get("models"):
                        st.write("Models available:", ", ".join(found["models"]))
                else:
                    st.error((found or {}).get("detail", "Could not reach it."))

        with st.form(f"cred_{provider}"):
            api_key = st.text_input(
                "API key", type="password",
                placeholder="leave blank to keep the saved key"
                            if (saved and saved["has_key"]) else "",
                help=_KEY_HELP.get(provider, ""),
                key=f"key_{provider}",
            )
            base_url = st.text_input(
                "Base URL" + (" (required)" if provider == "local" else " (optional)"),
                value=default_url,
                help="Only needed for a local server or a gateway such as "
                     "Azure OpenAI or OpenRouter.",
                key=f"url_{provider}",
            )
            model = st.text_input(
                "Model (optional)", value=(saved or {}).get("model") or "",
                placeholder="leave blank to use the server default",
                key=f"model_{provider}",
            )
            saved_now = st.form_submit_button("Save", type="primary")

        if saved_now:
            result = api_client.save_provider(
                provider,
                # None keeps the stored key; "" would clear it.
                api_key=api_key if api_key else None,
                base_url=base_url, model=model,
            )
            if result:
                st.success("Saved.")
                st.rerun()

        if saved:
            columns = st.columns(2)
            if columns[0].button("Test this key", key=f"test_{provider}"):
                with st.spinner("Making one small call..."):
                    outcome = api_client.test_provider(provider)
                if outcome and outcome["last_test_ok"]:
                    st.success("Works. " + (outcome.get("last_test_detail") or ""))
                elif outcome:
                    st.error(outcome.get("last_test_detail") or "Test failed.")
            if columns[1].button("Remove", key=f"del_{provider}"):
                if api_client.delete_provider(provider):
                    st.success("Removed.")
                    st.rerun()
            if saved.get("last_test_detail") and saved["last_test_ok"] is False:
                st.caption(f"Last test: {saved['last_test_detail']}")
