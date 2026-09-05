"""Settings - your Canvas connection."""
from __future__ import annotations

import streamlit as st

import sys
from pathlib import Path

# Streamlit puts only this file's directory on sys.path - see app.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend_streamlit.components import api_client
from frontend_streamlit.components.ui import page_setup, require_auth

page_setup("Canvas")
require_auth()

st.title("Canvas")
st.caption(
    "Connect your own Canvas account so approved grades can be pushed "
    "straight into your gradebook. Your token is yours: it is encrypted "
    "before it is stored and no one else on this instance can see or use it."
)

data = api_client.canvas_settings()
if data is None:
    st.stop()

# ---------------------------------------------------------------------
# Current state
# ---------------------------------------------------------------------
if data["connected"]:
    who = f" as **{data['canvas_user_name']}**" if data.get("canvas_user_name") else ""
    st.success(f"Connected to {data['base_url']}{who} "
               f"(token {data['masked_token']}).", icon=":material/link:")
    if data.get("last_test_ok") is False:
        st.warning(f"Last test failed: {data.get('last_test_detail')}")
elif data.get("server_fallback_available"):
    st.info(
        "You have not connected your own Canvas account, so grade pushes "
        "use the one configured on this server. That works on a "
        "single-instructor install; on a shared one, connect your own "
        "account below so grades go to *your* courses.",
        icon=":material/info:",
    )
else:
    st.info("Canvas is not connected. Grades can still be exported as CSV, "
            "Excel or PDF without it.", icon=":material/info:")

st.divider()

# ---------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------
st.subheader("Connect your Canvas account")

with st.expander("How do I get an access token?", expanded=not data["connected"]):
    st.markdown(
        """
        1. Sign in to Canvas in another tab.
        2. Click **Account** (your picture, top-left) → **Settings**.
        3. Scroll to **Approved Integrations** and click
           **+ New Access Token**.
        4. Purpose: `AutoGrade`. Leave the expiry blank, or set a date -
           you will need to make a new one when it expires.
        5. Click **Generate Token**, then **copy it immediately**. Canvas
           shows it once and never again.
        6. Paste it below.

        The token acts as you, so treat it like a password. You can revoke
        it from that same Canvas page at any time, which immediately stops
        AutoGrade being able to use it.
        """
    )

with st.form("canvas_connection"):
    base_url = st.text_input(
        "Canvas URL", value=data.get("base_url") or "",
        placeholder="https://canvas.your-university.edu",
        help="The address you use to open Canvas, without any path after it.",
    )
    api_token = st.text_input(
        "Access token", type="password",
        placeholder="leave blank to keep the saved token"
                    if data["connected"] else "paste the token from Canvas",
    )
    submitted = st.form_submit_button("Save", type="primary")

if submitted:
    if api_client.save_canvas_settings(base_url, api_token or None):
        st.success("Saved. Use **Test connection** to confirm it works.")
        st.rerun()

if data["connected"]:
    columns = st.columns(2)
    if columns[0].button("Test connection"):
        with st.spinner("Asking Canvas who this token belongs to..."):
            outcome = api_client.test_canvas_settings()
        if outcome and outcome.get("last_test_ok"):
            st.success(outcome.get("last_test_detail") or "Connected.")
            st.rerun()
        elif outcome:
            st.error(outcome.get("last_test_detail") or "Test failed.")
    if columns[1].button("Disconnect"):
        if api_client.delete_canvas_settings():
            st.success("Disconnected. Grades already pushed are unaffected.")
            st.rerun()

st.divider()
st.caption(
    "Once connected, set the **Canvas course ID** on your course and the "
    "**Canvas assignment ID** on the assignment, then use **5 · Export → "
    "Canvas** to sync your roster and push approved grades."
)
