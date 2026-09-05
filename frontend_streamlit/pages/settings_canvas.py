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
    "Optional. Connect Canvas and AutoGrade can put approved grades "
    "straight into your gradebook. Without it you can still download CSV, "
    "Excel and PDF, and upload those by hand."
)

data = api_client.canvas_settings()
if data is None:
    st.stop()

connected = bool(data["connected"])

# ---------------------------------------------------------------------
# Where things stand
# ---------------------------------------------------------------------
if connected:
    who = f" as **{data['canvas_user_name']}**" if data.get("canvas_user_name") else ""
    st.success(f"Connected to {data['base_url']}{who} "
               f"(token {data['masked_token']}).", icon=":material/link:")
    if data.get("last_test_ok") is False:
        st.error(f"The last test failed: {data.get('last_test_detail')}",
                 icon=":material/error:")
elif data.get("server_fallback_available"):
    st.info(
        "You have not connected your own Canvas account, so grade pushes "
        "use the one configured on this server.",
        icon=":material/info:",
    )
else:
    st.info("Canvas is not connected.", icon=":material/info:")

st.divider()

# ---------------------------------------------------------------------
# Getting a token
# ---------------------------------------------------------------------
with st.expander("Where do I get an access token?", expanded=not connected):
    st.markdown(
        """
        1. Open Canvas in another browser tab and sign in.
        2. Click **Account** (your picture, top-left), then **Settings**.
        3. Scroll down to **Approved Integrations**.
        4. Click **+ New Access Token**.
        5. Purpose: `AutoGrade`. Leave the expiry date blank, or set one and
           remember to make a new token when it runs out.
        6. Click **Generate Token**.
        7. **Copy the token now.** Canvas shows it once and never again.
        8. Paste it below.

        The token acts as you, in every course you teach, with permission to
        read and to change grades. Treat it like a password.
        """
    )

# ---------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------
if not connected:
    st.subheader("Connect your Canvas account")
    with st.form("canvas_connect"):
        base_url = st.text_input(
            "Canvas web address",
            value=data.get("base_url") or "",
            placeholder="https://canvas.your-university.edu",
            help="The address you use to open Canvas. Nothing after the "
                 "site name - no /courses/123.",
        )
        api_token = st.text_input(
            "Access token", type="password",
            placeholder="paste the token you copied from Canvas",
        )
        if st.form_submit_button("Connect", type="primary"):
            if not base_url.strip():
                st.error("Enter your Canvas web address.")
            elif not api_token.strip():
                st.error("Paste your access token.")
            elif api_client.save_canvas_settings(base_url, api_token):
                st.success("Saved. Testing it now would be a good idea.")
                st.rerun()
else:
    # --- connected: test, correct, replace, remove --------------------
    columns = st.columns(3)
    if columns[0].button("Test connection", type="primary"):
        with st.spinner("Asking Canvas who this token belongs to..."):
            outcome = api_client.test_canvas_settings()
        if outcome and outcome.get("last_test_ok"):
            st.success(outcome.get("last_test_detail") or "Connected.")
            st.rerun()
        elif outcome:
            st.error(outcome.get("last_test_detail") or "The test failed.")

    with st.expander("Change the Canvas web address"):
        st.caption("Your saved token is kept. You do not need to type it again.")
        with st.form("canvas_url"):
            new_url = st.text_input("Canvas web address",
                                    value=data.get("base_url") or "")
            if st.form_submit_button("Save address"):
                if api_client.save_canvas_settings(new_url, None):
                    st.success("Saved.")
                    st.rerun()

    with st.expander("Replace the token"):
        st.caption(
            "Use this when your token expired, when you revoked it, or when "
            "a test says it was rejected. The old one cannot be read back."
        )
        with st.form("canvas_token"):
            replacement = st.text_input("New access token", type="password")
            if st.form_submit_button("Replace token"):
                if not replacement.strip():
                    st.error("Paste the new token first.")
                elif api_client.save_canvas_settings(
                        data.get("base_url") or "", replacement):
                    st.success("Replaced. Test it to be sure.")
                    st.rerun()

    with st.expander("Remove this connection"):
        st.caption(
            "AutoGrade forgets your Canvas address and token. Grades already "
            "pushed to Canvas stay where they are.\n\n"
            "To make the token itself useless, delete it in Canvas as well: "
            "**Account -> Settings -> Approved Integrations**, click the bin "
            "beside `AutoGrade`."
        )
        if st.button("Remove connection"):
            if api_client.delete_canvas_settings():
                st.success("Removed.")
                st.rerun()

st.divider()
st.caption(
    "Your token is encrypted before it is stored, shown afterwards only as "
    "the last four characters, and never written to logs. Nobody else using "
    "this AutoGrade can see or use it."
)
st.caption(
    "Next: put the **Canvas course ID** on your course and the **Canvas "
    "assignment ID** on the assignment - both are the numbers in the Canvas "
    "web address - then use **5 · Export → Canvas** to sync your roster and "
    "push approved grades."
)
