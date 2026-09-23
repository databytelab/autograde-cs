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

page_setup("Dashboard")
require_auth()

st.title("Dashboard")

courses = api_client.list_courses()
if courses is None:
    st.stop()

if not courses:
    st.info("You have no courses yet.")
    page_link("pages/new_assignment.py", label="Create your first course",
                 icon=":material/note_add:")
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
        else:
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
            if stats:
                stats_row(stats)

                if stats["errored"]:
                    st.warning(
                        f"{stats['errored']} submission(s) could not be parsed "
                        f"or graded. See **Upload & grade** for the reason."
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
                    page_link("pages/upload_grade.py", label="Upload & grade", icon=":material/upload_file:")
                with links[1]:
                    page_link("pages/review_results.py", label="Review results", icon=":material/fact_check:")
                with links[2]:
                    page_link("pages/export.py", label="Export", icon=":material/download:")

            # ----- Manage the selected assignment -------------------------
            # A toggle, not an expander: the course card is already an
            # expander and Streamlit forbids nesting them.
            aid = assignment["id"]
            if st.toggle("⚙ Manage this assignment", key=f"mng_{aid}"):
                rub = assignment.get("rubric_json") or {}
                n_crit = len(rub.get("criteria", []))
                st.markdown(
                    f"**Rubric:** {rub.get('title') or '(default)'} — "
                    f"{n_crit} criteria, "
                    f"{assignment['total_possible_points']:g} points"
                )
                sol_path = assignment.get("expected_submission_path")
                if sol_path:
                    st.caption(
                        f"Reference solution attached: `{Path(sol_path).name}`"
                    )
                else:
                    st.caption(
                        "No reference solution attached. Attaching one lets "
                        "grading compare against it and lets you build a "
                        "per-question rubric."
                    )

                new_sol = st.file_uploader(
                    "Attach or replace the reference solution "
                    "(.ipynb / .html / .py)",
                    type=["ipynb", "html", "htm", "py"], key=f"sol_up_{aid}",
                )
                rebuild = st.checkbox(
                    "Also rebuild the rubric from this file "
                    "(one criterion per numbered question)",
                    value=True, key=f"rebuild_{aid}",
                )
                if new_sol is not None and st.button(
                    "Save solution", key=f"savesol_{aid}", type="primary"
                ):
                    with st.spinner("Saving solution…"):
                        ok = api_client.upload_solution(aid, new_sol)
                    if ok and rebuild:
                        with st.spinner("Rebuilding the rubric from the solution…"):
                            draft = api_client.preview_rubric_from_solution(
                                new_sol,
                                float(assignment["total_possible_points"]),
                            )
                        if draft:
                            api_client.update_assignment(
                                aid, {"rubric_json": draft})
                    if ok:
                        st.success("Saved. Re-grade the assignment to use it.")
                        st.rerun()

                st.divider()
                st.markdown("**Danger zone**")
                del_ok = st.checkbox(
                    "Yes, permanently delete this assignment and all its "
                    "submissions and grades", key=f"delok_{aid}",
                )
                if st.button("Delete assignment", key=f"del_{aid}",
                             disabled=not del_ok):
                    if api_client.delete_assignment(aid) is not None:
                        st.success("Assignment deleted.")
                        st.rerun()

        # ----- Delete the course itself (always available) ----------------
        if st.toggle(f"⚙ Delete course “{course['name']}”",
                     key=f"mngc_{course['id']}"):
            st.caption(
                "Deleting a course removes every assignment, submission, and "
                "grade inside it. This cannot be undone."
            )
            course_del_ok = st.checkbox(
                f"Yes, permanently delete “{course['name']}” and everything "
                "in it", key=f"delcourseok_{course['id']}",
            )
            if st.button("Delete course", key=f"delcourse_{course['id']}",
                         disabled=not course_del_ok):
                if api_client.delete_course(course["id"]) is not None:
                    st.success("Course deleted.")
                    st.rerun()
