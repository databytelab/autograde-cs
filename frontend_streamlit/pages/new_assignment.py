"""Create courses and assignments, and build the rubric."""
from __future__ import annotations

import json

import streamlit as st

import sys
from pathlib import Path

# Streamlit puts only this file's directory on sys.path - see app.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend_streamlit.components import api_client
from frontend_streamlit.components.ui import page_link, course_selector, page_setup, require_auth

page_setup("New assignment", "📝")
require_auth()

st.title("📝 New assignment")

# ---------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------
with st.expander("Courses", expanded=False):
    with st.form("new_course"):
        st.markdown("**Create a course**")
        columns = st.columns([3, 2, 2])
        name = columns[0].text_input("Name", placeholder="CS 231N Computer Vision")
        term = columns[1].text_input("Term", placeholder="Fall 2025")
        canvas_id = columns[2].text_input(
            "Canvas course ID", placeholder="optional",
            help="Needed only if you plan to push grades back to Canvas.",
        )
        if st.form_submit_button("Create course", type="primary"):
            if not name.strip():
                st.error("A course needs a name.")
            elif api_client.create_course(name, term, canvas_id):
                st.success(f"Created {name}.")
                st.rerun()

course = course_selector()
if course is None:
    st.stop()

st.divider()

# ---------------------------------------------------------------------
# The rubric
# ---------------------------------------------------------------------
st.subheader("Rubric")
st.caption(
    "The rubric is what the grader is held to. It never invents criteria of "
    "its own, and it can never award more than a criterion's maximum."
)

if "draft_rubric" not in st.session_state:
    st.session_state["draft_rubric"] = None

method = st.radio(
    "How do you want to define it?",
    ["Describe the assignment (AI builds the rubric)",
     "Paste rubric JSON",
     "Use the default CS rubric"],
    horizontal=False,
)

# -- Option A: prose -> AI ---------------------------------------------
if method.startswith("Describe"):
    prose = st.text_area(
        "Assignment description",
        height=220,
        placeholder=(
            "Load housing.csv with pandas and print its shape (20 points).\n"
            "Implement closed-form OLS as fit(X, y) and report R-squared "
            "(50 points).\n"
            "Plot predicted vs actual values with labelled axes (20 points).\n"
            "Write a short paragraph interpreting the result (10 points)."
        ),
    )
    target_points = st.number_input("Total points", 1.0, 1000.0, 100.0, step=5.0)

    if st.button("Generate rubric", type="primary", disabled=len(prose.strip()) < 10):
        with st.spinner("Reading the assignment and extracting criteria..."):
            draft = api_client.preview_rubric(prose, target_points)
        if draft:
            st.session_state["draft_rubric"] = draft
            st.session_state["draft_raw_text"] = prose

# -- Option B: raw JSON --------------------------------------------------
elif method.startswith("Paste"):
    pasted = st.text_area(
        "Rubric JSON", height=300,
        placeholder=json.dumps({
            "title": "HW3",
            "criteria": [
                {"id": "loading", "name": "Data loading",
                 "description": "Reads the CSV and reports its shape",
                 "max_points": 20, "requires_output": True},
                {"id": "model", "name": "Model fitting",
                 "description": "Implements OLS correctly", "max_points": 80},
            ],
            "grading_notes": "Strict on correctness, generous on style.",
        }, indent=2),
    )
    if st.button("Validate rubric", type="primary", disabled=not pasted.strip()):
        try:
            st.session_state["draft_rubric"] = json.loads(pasted)
            st.session_state["draft_raw_text"] = None
            st.success("Parsed. Check the preview below, then create the assignment.")
        except json.JSONDecodeError as exc:
            st.error(f"That is not valid JSON: {exc}")

# -- Option C: default ---------------------------------------------------
else:
    default_points = st.number_input(
        "Total points", 1.0, 1000.0, 100.0, step=5.0, key="default_points"
    )
    st.info(
        "Four generic criteria - correctness, completeness, code quality, and "
        "explanation - split evenly. Fine for a quick run; a rubric of your "
        "own will grade far more accurately."
    )
    if st.button("Use the default rubric", type="primary"):
        st.session_state["draft_rubric"] = None
        st.session_state["draft_raw_text"] = None
        st.session_state["use_default_points"] = default_points

# ---------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------
draft = st.session_state.get("draft_rubric")
if draft:
    st.divider()
    st.subheader("Rubric preview")

    total = draft.get("total_points") or sum(
        c.get("max_points", 0) for c in draft.get("criteria", [])
    )
    st.markdown(f"**{draft.get('title', 'Untitled')}** — {total:g} points total")

    for warning in draft.get("warnings", []):
        st.warning(warning)

    for criterion in draft.get("criteria", []):
        with st.container(border=True):
            head = st.columns([4, 1])
            head[0].markdown(f"**{criterion.get('name')}**")
            head[1].markdown(f"`{criterion.get('max_points'):g} pts`")
            if criterion.get("description"):
                st.caption(criterion["description"])
            marks = []
            if criterion.get("requires_output"):
                marks.append("must have been executed")
            if criterion.get("keywords"):
                marks.append("looks for: " + ", ".join(criterion["keywords"]))
            if marks:
                st.caption(" · ".join(marks))

    with st.expander("Raw JSON"):
        st.code(json.dumps(draft, indent=2), language="json")

# ---------------------------------------------------------------------
# Create the assignment
# ---------------------------------------------------------------------
st.divider()
st.subheader("Create the assignment")

with st.form("new_assignment"):
    assignment_name = st.text_input("Assignment name",
                                    placeholder="HW3 - Linear Regression")
    description = st.text_area(
        "Description (shown to the grader for context)", height=100
    )
    columns = st.columns(3)
    points = columns[0].number_input("Points", 1.0, 1000.0, 100.0, step=5.0)
    due_date = columns[1].date_input("Due date", value=None)
    canvas_assignment_id = columns[2].text_input(
        "Canvas assignment ID", placeholder="optional"
    )

    if st.form_submit_button("Create assignment", type="primary"):
        if not assignment_name.strip():
            st.error("The assignment needs a name.")
            st.stop()

        payload = {
            "course_id": course["id"],
            "name": assignment_name.strip(),
            "description": description or None,
            "total_possible_points": points,
            "due_date": f"{due_date}T23:59:59" if due_date else None,
            "canvas_assignment_id": canvas_assignment_id or None,
        }
        if draft:
            payload["rubric_json"] = draft

        with st.spinner("Creating..."):
            created = api_client.create_assignment(payload)

        if created:
            st.session_state["active_assignment"] = created["id"]
            st.session_state["draft_rubric"] = None
            st.success(
                f"Created **{created['name']}** "
                f"({created['total_possible_points']:g} points)."
            )
            page_link("pages/upload_grade.py",
                         label="Next: upload submissions", icon="📤")
