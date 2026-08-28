"""Dashboard - every course and assignment at a glance."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import sys
from pathlib import Path

# Streamlit puts only this file's directory on sys.path - see app.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend_streamlit.components import api_client
from frontend_streamlit.components.ui import (
    page_link,
    GRADE_COLORS,
    page_setup,
    require_auth,
    stats_row,
)

page_setup("Dashboard", "📊")
require_auth()

st.title("📊 Dashboard")

courses = api_client.list_courses()
if courses is None:
    st.stop()

if not courses:
    st.info("You have no courses yet.")
    page_link("pages/new_assignment.py", label="Create your first course",
                 icon="📝")
    st.stop()

assignments = api_client.list_assignments() or []
by_course: dict[str, list[dict]] = {}
for assignment in assignments:
    by_course.setdefault(assignment["course_id"], []).append(assignment)

# ---------------------------------------------------------------------
# Headline numbers
# ---------------------------------------------------------------------
total_submissions = sum(a["submission_count"] for a in assignments)
total_graded = sum(a["graded_count"] for a in assignments)

columns = st.columns(4)
columns[0].metric("Courses", len(courses))
columns[1].metric("Assignments", len(assignments))
columns[2].metric("Submissions", total_submissions)
columns[3].metric(
    "Graded",
    f"{total_graded}/{total_submissions}" if total_submissions else "0",
)

st.divider()

# ---------------------------------------------------------------------
# Per course
# ---------------------------------------------------------------------
for course in courses:
    course_assignments = by_course.get(course["id"], [])
    header = course["name"] + (f"  ·  {course['term']}" if course.get("term") else "")

    with st.expander(f"**{header}**  —  {len(course_assignments)} assignment(s)",
                     expanded=True):
        if not course_assignments:
            st.caption("No assignments yet.")
            continue

        table = pd.DataFrame([{
            "Assignment": a["name"],
            "Status": a["status"],
            "Submissions": a["submission_count"],
            "Graded": a["graded_count"],
            "Points": a["total_possible_points"],
            "Due": (a["due_date"] or "")[:10],
        } for a in course_assignments])
        st.dataframe(table, use_container_width=True, hide_index=True)

        names = {a["name"]: a for a in course_assignments}
        chosen = st.selectbox(
            "Show details for", list(names), key=f"detail_{course['id']}"
        )
        assignment = names[chosen]

        stats = api_client.get_stats(assignment["id"])
        if not stats:
            continue

        stats_row(stats)

        if stats["errored"]:
            st.warning(
                f"{stats['errored']} submission(s) could not be parsed or graded. "
                f"See **Upload & grade** for the reason on each."
            )

        distribution = stats.get("grade_distribution") or {}
        if distribution:
            order = [g for g in GRADE_COLORS if g in distribution]
            chart = pd.DataFrame(
                {"Students": [distribution[g] for g in order]}, index=order
            )
            st.bar_chart(chart, height=220)

        links = st.columns(3)
        with links[0]:
            page_link("pages/upload_grade.py", label="Upload & grade", icon="📤")
        with links[1]:
            page_link("pages/review_results.py", label="Review results", icon="🔍")
        with links[2]:
            page_link("pages/export.py", label="Export", icon="📦")
