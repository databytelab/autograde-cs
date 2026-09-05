"""Settings - AI providers. Choose what grades your submissions."""
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
st.caption(
    "AutoGrade needs one AI account to read submissions and propose grades. "
    "Set it up once here. You never have to edit a file."
)

data = api_client.provider_settings()
if data is None:
    st.stop()

by_provider = {c["provider"]: c for c in data["credentials"]}
server_available = bool(data["administrator_available"])
preferred = data["preferred_provider"]

NAMES = {
    "openai": "OpenAI",
    "anthropic": "Claude",
    "local": "Local model (Ollama)",
}

# Short, current lists. "Other" is always available, because a provider
# adds models faster than any drop-down can be maintained.
MODELS = {
    "openai": [
        ("gpt-4o", "Recommended. Reads code, output and figures."),
        ("gpt-4o-mini", "Cheaper and faster. Slightly less careful."),
    ],
    "anthropic": [
        ("claude-opus-5", "Recommended. The most careful grader."),
        ("claude-sonnet-5", "Faster and cheaper. Very good."),
        ("claude-haiku-4-5-20251001", "Cheapest. Best for a quick trial."),
    ],
}
DEFAULT_MODEL = {"openai": "gpt-4o", "anthropic": "claude-opus-5"}
OTHER = "Other (type a model name)"

WHERE_TO_GET = {
    "openai": (
        "1. Go to **platform.openai.com/api-keys** and sign in.\n"
        "2. Click **Create new secret key**, name it `AutoGrade`.\n"
        "3. Copy it immediately - it is shown once.\n"
        "4. Add a payment method under **Settings -> Billing**.\n\n"
        "**A ChatGPT Plus subscription does not include API access.** "
        "They are billed separately. Grading a class of 30 typically costs "
        "well under one US dollar."
    ),
    "anthropic": (
        "1. Go to **console.anthropic.com** and sign in.\n"
        "2. Open **API keys** and click **Create key**, name it `AutoGrade`.\n"
        "3. Copy it immediately - it is shown once.\n"
        "4. Add credit under **Billing**.\n\n"
        "**A Claude Pro subscription does not include API access.** "
        "They are billed separately."
    ),
}


def _active_label() -> str:
    if preferred:
        return f"your own {NAMES.get(preferred, preferred)} account"
    if server_available:
        return (f"the shared {NAMES.get(data['administrator_provider'], '')} "
                "account set up on this server")
    return ""


# ---------------------------------------------------------------------
# What is grading right now
# ---------------------------------------------------------------------
if preferred and by_provider.get(preferred):
    saved = by_provider[preferred]
    detail = saved["model"] or "the default model"
    st.success(f"**Grading is set up.** Using {_active_label()}, model "
               f"`{detail}`.", icon=":material/check_circle:")
elif server_available:
    st.success(f"**Grading is set up.** Using {_active_label()}. You do not "
               "need an account of your own.", icon=":material/check_circle:")
else:
    st.warning(
        "**Grading is not set up yet.** Choose one of the three tabs below "
        "and follow the steps. Everything else in AutoGrade - uploading, "
        "rubrics, exports - works without this.",
        icon=":material/priority_high:",
    )

st.divider()


# ---------------------------------------------------------------------
# One tab per provider
# ---------------------------------------------------------------------
def _status_line(provider: str) -> None:
    saved = by_provider.get(provider)
    if not saved:
        st.info("Not set up yet.", icon=":material/info:")
        return

    bits = []
    if saved["has_key"]:
        bits.append(f"Key saved, ending `{saved['masked_key'][-4:]}`")
    if saved["base_url"]:
        bits.append(f"Server `{saved['base_url']}`")
    if saved["model"]:
        bits.append(f"Model `{saved['model']}`")
    summary = " · ".join(bits) or "Saved"

    if saved["last_test_ok"] is True:
        st.success(f"{summary} · tested and working.", icon=":material/check:")
    elif saved["last_test_ok"] is False:
        st.error(f"{summary}\n\nLast test failed: "
                 f"{saved.get('last_test_detail') or 'no detail'}",
                 icon=":material/error:")
    else:
        st.info(f"{summary} · not tested yet.", icon=":material/info:")


def _use_button(provider: str, *, key: str) -> None:
    """Make this the account that grades."""
    if preferred == provider:
        st.caption("This is what grades your submissions.")
        return
    if st.button("Use this for grading", key=key, type="primary"):
        if api_client.set_provider_preference(provider):
            st.success("Done. Your submissions will be graded with this.")
            st.rerun()


def _model_picker(provider: str, current: str | None) -> str:
    choices = MODELS.get(provider, [])
    labels = [f"{name} — {note}" for name, note in choices] + [OTHER]
    names = [name for name, _ in choices]

    index = names.index(current) if current in names else (
        len(labels) - 1 if current else 0)
    picked = st.selectbox("Model", labels, index=index, key=f"model_pick_{provider}")
    if picked == OTHER:
        return st.text_input(
            "Model name", value=current or "", key=f"model_free_{provider}",
            placeholder=DEFAULT_MODEL.get(provider, ""),
            help="Any model your account can call.",
        ).strip()
    return names[labels.index(picked)]


def _cloud_tab(provider: str) -> None:
    saved = by_provider.get(provider)
    _status_line(provider)

    with st.expander("Where do I get an API key?",
                     expanded=not saved):
        st.markdown(WHERE_TO_GET[provider])

    # --- the key -----------------------------------------------------
    if not saved or not saved["has_key"]:
        with st.form(f"key_{provider}"):
            new_key = st.text_input(
                "API key", type="password",
                placeholder="sk-..." if provider == "openai" else "sk-ant-...",
                help="Pasted keys are encrypted before they are stored and "
                     "are never shown again.",
            )
            model = _model_picker(provider, DEFAULT_MODEL.get(provider))
            if st.form_submit_button("Save key", type="primary"):
                if not new_key.strip():
                    st.error("Paste your API key first.")
                elif api_client.save_provider(provider, api_key=new_key,
                                              model=model):
                    # On a single-professor installation there is no shared
                    # account to fall back on, so saving a key and then not
                    # being able to grade would be nonsense. On a shared
                    # server the two stay separate, so pasting a key can
                    # never silently redirect someone else's spend.
                    if not server_available:
                        api_client.set_provider_preference(provider)
                    st.success("Saved.")
                    st.rerun()
        return

    # --- already saved ------------------------------------------------
    with st.form(f"model_{provider}"):
        model = _model_picker(provider, saved["model"])
        if st.form_submit_button("Save model"):
            if api_client.save_provider(provider, model=model):
                st.success("Saved.")
                st.rerun()

    columns = st.columns(3)
    if columns[0].button("Test connection", key=f"test_{provider}"):
        with st.spinner("Making one small call..."):
            outcome = api_client.test_provider(provider)
        if outcome and outcome["last_test_ok"]:
            st.success(outcome.get("last_test_detail") or "Working.")
            st.rerun()
        elif outcome:
            st.error(outcome.get("last_test_detail") or "The test failed.")

    with columns[1]:
        _use_button(provider, key=f"use_{provider}")

    with st.expander("Replace this key"):
        st.caption("Use this if you regenerated your key, or if the test "
                   "says it was rejected. The old one cannot be read back.")
        with st.form(f"replace_{provider}"):
            replacement = st.text_input("New API key", type="password")
            if st.form_submit_button("Replace key"):
                if not replacement.strip():
                    st.error("Paste the new key first.")
                elif api_client.save_provider(provider, api_key=replacement):
                    st.success("Replaced. Test it to be sure.")
                    st.rerun()

    with st.expander("Remove this key"):
        st.caption("AutoGrade forgets the key. Nothing else is deleted. "
                   "Revoke it at the provider too if it is no longer needed.")
        if st.button("Remove key", key=f"remove_{provider}"):
            if api_client.delete_provider(provider):
                st.success("Removed.")
                st.rerun()


def _local_tab() -> None:
    saved = by_provider.get("local")
    _status_line("local")

    st.caption("A model that runs on your own computer. No API key, no "
               "per-use cost, and nothing leaves your machine.")

    with st.expander("How do I install Ollama and download a model?",
                     expanded=not saved):
        st.markdown(
            "1. Download Ollama from **ollama.com/download** and install it. "
            "It runs in the background whenever your computer is on.\n"
            "2. Open **PowerShell** and run:\n"
            "   ```\n   ollama pull qwen2.5-coder:7b\n   ```\n"
            "   That downloads about 5 GB, once.\n"
            "3. Check what you have:\n"
            "   ```\n   ollama list\n   ```\n"
            "4. Come back here and click **Detect models** below.\n\n"
            "**How much computer do you need?**\n\n"
            "| Model | Memory needed | Notes |\n"
            "|---|---|---|\n"
            "| `qwen2.5:3b` | about 4 GB | Fastest. Marks generously - check it |\n"
            "| `qwen2.5-coder:7b` | about 8 GB | The sensible default |\n"
            "| `qwen2.5-coder:14b` | about 16 GB | Better, needs a strong machine |\n\n"
            "A graphics card makes it much faster but is not required. "
            "Local models grade more slowly than OpenAI or Claude, and are "
            "more lenient - spot-check a few grades before trusting one with "
            "real coursework."
        )

    # AutoGrade runs inside Docker, so "localhost" means the container.
    default_url = (saved or {}).get("base_url") or "http://host.docker.internal:11434/v1"
    url = st.text_input(
        "Ollama address", value=default_url,
        help="Leave this as it is if Ollama runs on this same computer.",
    )
    st.caption(
        "AutoGrade runs inside Docker, where `localhost` means AutoGrade "
        "itself. `host.docker.internal` is how it reaches your computer. "
        "If Ollama runs on a different machine, put that machine's address "
        "here instead, for example `http://192.168.1.20:11434/v1`."
    )

    models: list[str] = []
    if st.button("Detect models", type="primary"):
        with st.spinner("Asking Ollama what it has..."):
            found = api_client.discover_local_models(url)
        if found and found.get("reachable"):
            models = [m for m in found.get("models") or []]
            st.session_state["ollama_models"] = models
            st.session_state["ollama_url"] = url
            if models:
                st.success(f"Found {len(models)} model(s).")
            else:
                st.warning("Ollama answered, but no models are downloaded "
                           "yet. Run `ollama pull qwen2.5-coder:7b` first.")
        else:
            st.error((found or {}).get("detail")
                     or "Could not reach Ollama at that address.")
            st.caption("Check that Ollama is installed and running - its "
                       "icon appears in the Windows system tray.")

    models = st.session_state.get("ollama_models", models)
    current = (saved or {}).get("model") or ""

    if models:
        options = models + [OTHER]
        index = models.index(current) if current in models else 0
        picked = st.selectbox("Model to grade with", options, index=index)
        model = st.text_input("Model name", value=current) if picked == OTHER else picked
    else:
        model = st.text_input(
            "Model to grade with", value=current or "qwen2.5-coder:7b",
            help="Click Detect models above to choose from a list.",
        )

    if st.button("Save", type="primary", key="save_local"):
        if not url.strip():
            st.error("Enter the Ollama address.")
        elif api_client.save_provider("local", api_key="", base_url=url,
                                      model=model):
            if not server_available:
                api_client.set_provider_preference("local")
            st.success("Saved.")
            st.rerun()

    if saved:
        columns = st.columns(3)
        if columns[0].button("Test connection", key="test_local"):
            with st.spinner("Grading one tiny sample..."):
                outcome = api_client.test_provider("local")
            if outcome and outcome["last_test_ok"]:
                st.success(outcome.get("last_test_detail") or "Working.")
                st.rerun()
            elif outcome:
                st.error(outcome.get("last_test_detail") or "The test failed.")
        with columns[1]:
            _use_button("local", key="use_local")
        with columns[2]:
            if st.button("Remove", key="remove_local"):
                if api_client.delete_provider("local"):
                    st.success("Removed.")
                    st.rerun()


openai_tab, claude_tab, local_tab = st.tabs(
    ["OpenAI", "Claude", "Local model (Ollama)"])
with openai_tab:
    _cloud_tab("openai")
with claude_tab:
    _cloud_tab("anthropic")
with local_tab:
    _local_tab()


# ---------------------------------------------------------------------
# The shared account, where there is one
# ---------------------------------------------------------------------
if server_available:
    st.divider()
    st.subheader("The shared account on this server")
    admin_name = NAMES.get(data["administrator_provider"],
                           data["administrator_provider"])
    st.caption(f"Whoever runs this server has set up a shared {admin_name} "
               "account. You can use it instead of your own key; the cost "
               "goes to them, not to you.")
    if preferred is None:
        st.info("You are using it now.", icon=":material/check:")
    elif st.button("Use the shared account instead"):
        if api_client.set_provider_preference(None):
            st.success("Switched.")
            st.rerun()

st.divider()
st.caption(
    "Keys are encrypted before they are stored, shown afterwards only as "
    "the last four characters, and never written to logs. There is no way "
    "to read one back - if you lose it, replace it."
)
