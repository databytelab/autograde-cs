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
from frontend_streamlit.components.landing import render_landing
from frontend_streamlit.components.ui import (
    grading_key_hint,
    grading_ready,
    page_link,
    page_setup,
    render_sidebar,
)

page_setup("Home")


# ---------------------------------------------------------------------
# Signed out - the marketing / sign-in surface.
#
# Rendered first and then stopped, so none of the application chrome
# (sidebar navigation, backend status) is created for a visitor who has
# not signed in. See components/landing.py.
# ---------------------------------------------------------------------
if not st.session_state.get("token"):
    render_landing()
    st.stop()


# ---------------------------------------------------------------------
# Signed in - the application home
# ---------------------------------------------------------------------
user = st.session_state["user"]
render_sidebar(user)

st.title("AutoGrade CS")
st.markdown(
    "<p style='font-size:1.15rem; line-height:1.55; color:#6b675f; "
    "margin:-2px 0 14px 0;'>AI-assisted grading for CS assignments "
    "&mdash; you stay in control of every grade.</p>",
    unsafe_allow_html=True,
)

st.success(f"Signed in as **{user['name']}**")

status = api_client.health()
if status and not grading_ready(status):
    key_hint = grading_key_hint(status)
    provider = status.get("llm_provider", "the AI")
    st.warning(
        f"**Grading is disabled.** The {provider} backend is not configured. "
        f"Set `{key_hint}` in your `.env` file (or switch `LLM_PROVIDER`) and "
        "restart the server. Everything else - uploading, similarity "
        "detection, export - works without it."
    )

st.subheader("Where to start")
columns = st.columns(5)
with columns[0]:
    page_link("pages/dashboard.py", label="Dashboard", icon=":material/space_dashboard:")
    st.caption("See every course and how grading is going.")
with columns[1]:
    page_link("pages/new_assignment.py", label="New assignment", icon=":material/note_add:")
    st.caption("Create a course or assignment and write its rubric.")
with columns[2]:
    page_link("pages/upload_grade.py", label="Upload & grade", icon=":material/upload_file:")
    st.caption("Upload student files and run the grader.")
with columns[3]:
    page_link("pages/review_results.py", label="Review results", icon=":material/fact_check:")
    st.caption("Read the feedback, adjust scores, approve grades.")
with columns[4]:
    page_link("pages/export.py", label="Export", icon=":material/download:")
    st.caption("Download CSV, Excel, PDF, or push to Canvas.")

st.divider()
with st.expander("How grading works"):
    st.markdown(
        """
        1. **Parse** - your students' `.ipynb`, `.html` and `.py` files are
           broken into cells, code, prose, outputs and figures.
        2. **Grade** - each submission goes to the model once, together with
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
