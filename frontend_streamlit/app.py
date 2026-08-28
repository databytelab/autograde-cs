"""
AutoGrade CS - Streamlit MVP Frontend

Run with:
    streamlit run frontend_streamlit/app.py

The FastAPI backend must be running too:
    uvicorn backend.main:app --reload
"""
from __future__ import annotations

import streamlit as st

import sys
from pathlib import Path

# Streamlit puts only this file's directory on sys.path, so the project
# root has to be added before any `frontend_streamlit.*` import works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frontend_streamlit.components import api_client
from frontend_streamlit.components.ui import page_link, page_setup, render_sidebar

page_setup("Home")

st.title("🎓 AutoGrade CS")
st.caption("AI-assisted grading for CS assignments - you stay in control of every grade.")


# ---------------------------------------------------------------------
# Signed in
# ---------------------------------------------------------------------
if st.session_state.get("token"):
    user = st.session_state["user"]
    render_sidebar(user)

    st.success(f"Signed in as **{user['name']}**")

    status = api_client.health()
    if status and not status.get("anthropic_configured"):
        st.warning(
            "**Grading is disabled.** No Anthropic API key is configured on the "
            "backend. Add `ANTHROPIC_API_KEY=...` to your `.env` file and "
            "restart the server. Everything else - uploading, similarity "
            "detection, export - works without it."
        )

    st.subheader("Where to start")
    columns = st.columns(5)
    with columns[0]:
        page_link("pages/dashboard.py", label="Dashboard", icon="📊")
        st.caption("See every course and how grading is going.")
    with columns[1]:
        page_link("pages/new_assignment.py", label="New assignment", icon="📝")
        st.caption("Create a course or assignment and write its rubric.")
    with columns[2]:
        page_link("pages/upload_grade.py", label="Upload & grade", icon="📤")
        st.caption("Upload student files and run the grader.")
    with columns[3]:
        page_link("pages/review_results.py", label="Review results", icon="🔍")
        st.caption("Read the feedback, adjust scores, approve grades.")
    with columns[4]:
        page_link("pages/export.py", label="Export", icon="📦")
        st.caption("Download CSV, Excel, PDF, or push to Canvas.")

    st.divider()
    with st.expander("How grading works"):
        st.markdown(
            """
            1. **Parse** - your students' `.ipynb`, `.html` and `.py` files are
               broken into cells, code, prose, outputs and figures.
            2. **Grade** - each submission goes to Claude once, together with
               your rubric. The model scores every criterion and writes
               feedback and its reasoning.
            3. **Verify** - AutoGrade recomputes every total itself, clamps any
               score above a criterion's maximum, and fills in any criterion
               the model skipped. The model never does arithmetic that counts.
            4. **Review** - you read the feedback, override anything you
               disagree with, and approve. The AI's original scores are kept
               alongside your changes, so the record always shows both.

            Nothing is pushed to Canvas or handed to a student until you
            finalize it.
            """
        )

    st.stop()


# ---------------------------------------------------------------------
# Signed out
# ---------------------------------------------------------------------
status = api_client.health()
if status is None:
    st.error(
        f"The backend at `{api_client.API_BASE}` is not responding.\n\n"
        "Start it in another terminal:\n\n"
        "```\nuvicorn backend.main:app --reload\n```"
    )
    st.stop()

sign_in, sign_up = st.tabs(["Sign in", "Create an account"])

with sign_in:
    with st.form("sign_in"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            if api_client.login(email, password):
                st.rerun()

with sign_up:
    with st.form("sign_up"):
        new_name = st.text_input("Full name")
        new_email = st.text_input("Email", key="new_email")
        new_password = st.text_input(
            "Password", type="password", key="new_password",
            help="8-72 characters.",
        )
        role = st.selectbox(
            "Role", ["professor", "ta"],
            help="TAs can grade and leave notes. Only professors can approve "
                 "a grade or delete a course.",
        )
        if st.form_submit_button("Create account", type="primary"):
            if not new_name.strip():
                st.error("Please enter your name.")
            elif len(new_password) < 8:
                st.error("Password must be at least 8 characters.")
            elif api_client.register(new_email, new_name, new_password, role):
                st.rerun()
