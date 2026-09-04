"""Upload student submissions and run the grader."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import sys
from html import escape
from pathlib import Path

# Streamlit puts only this file's directory on sys.path - see app.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend_streamlit.components import api_client
from frontend_streamlit.components.ui import (
    page_link,
    assignment_selector,
    course_selector,
    flag_chips,
    grading_ready,
    page_setup,
    require_auth,
)

page_setup("Upload & grade")
require_auth()

st.title("Upload & grade")

course = course_selector()
if course is None:
    st.stop()

assignment = assignment_selector(course["id"])
if assignment is None:
    page_link("pages/new_assignment.py", label="Create an assignment", icon=":material/note_add:")
    st.stop()

health = api_client.health() or {}
grading_available = grading_ready(health)

st.divider()

# ---------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------
st.subheader("1 · Upload submissions")

uploaded = st.file_uploader(
    "Student files",
    type=["ipynb", "html", "htm", "py", "zip"],
    accept_multiple_files=True,
    help="Drop individual files, or a .zip (e.g. Canvas 'Download "
         "Submissions') - a zip is unpacked into one submission per file "
         "inside. Student names are guessed from the filename and can be "
         "corrected below.",
)

if uploaded and st.button(f"Upload {len(uploaded)} file(s)", type="primary"):
    with st.spinner("Uploading..."):
        outcome = api_client.upload_submissions(assignment["id"], uploaded)
    if outcome:
        st.success(f"Uploaded {outcome['uploaded']} file(s).")
        if outcome["failed"]:
            st.error(f"{outcome['failed']} file(s) were rejected:")
            for result in outcome["results"]:
                if not result["ok"]:
                    st.markdown(f"- `{result['filename']}` — {result['error']}")
        st.rerun()

with st.expander("Instructor reference solution (optional, improves accuracy)"):
    st.caption(
        "Upload your own solved notebook. The grader treats its outputs as "
        "the expected result, which makes correctness judgements markedly "
        "more reliable than rubric text alone."
    )
    solution = st.file_uploader("Solution file", type=["ipynb", "html", "py"],
                                key="solution_upload")
    if solution and st.button("Attach solution"):
        if api_client.upload_solution(assignment["id"], solution):
            st.success("Attached.")
            st.rerun()

if assignment.get("expected_submission_path"):
    st.success("A reference solution is attached to this assignment.",
               icon=":material/check_circle:")

# ---------------------------------------------------------------------
# Current submissions
# ---------------------------------------------------------------------
st.divider()
st.subheader("2 · Submissions")

submissions = api_client.list_submissions(assignment["id"])
if submissions is None:
    st.stop()

if not submissions:
    st.info("No submissions uploaded yet.")
    st.stop()

table = pd.DataFrame([{
    "Student": s["student_name"] or "(unknown)",
    "File": s["original_filename"],
    "Type": s["file_type"],
    "Status": s["status"],
    "Size (KB)": round((s["file_size_bytes"] or 0) / 1024, 1),
    "Error": (s["error_message"] or "")[:90],
} for s in submissions])
st.dataframe(table, use_container_width=True, hide_index=True)

errored = [s for s in submissions if s["status"] == "error"]
if errored:
    st.warning(
        f"{len(errored)} submission(s) failed. They stay in the list so you "
        f"can see who needs to resubmit."
    )

with st.expander("Correct a student name or email"):
    by_label = {
        f"{s['student_name'] or '(unknown)'} — {s['original_filename']}": s
        for s in submissions
    }
    chosen = st.selectbox("Submission", list(by_label))
    target = by_label[chosen]
    columns = st.columns([2, 2, 2, 1])
    fixed_name = columns[0].text_input("Name", value=target["student_name"] or "")
    fixed_email = columns[1].text_input("Email", value=target["student_email"] or "")
    fixed_id = columns[2].text_input(
        "Canvas user ID", value=target["student_id_external"] or ""
    )
    columns[3].write("")
    if columns[3].button("Save"):
        if api_client.update_submission(target["id"], {
            "student_name": fixed_name or None,
            "student_email": fixed_email or None,
            "student_id_external": fixed_id or None,
        }):
            st.success("Updated.")
            st.rerun()

    if st.button("Delete this submission", type="secondary"):
        if api_client.delete_submission(target["id"]) is not None:
            st.success("Deleted.")
            st.rerun()

# ---------------------------------------------------------------------
# Grade
# ---------------------------------------------------------------------
st.divider()
st.subheader("3 · Grade")

ungraded = [s for s in submissions if s["status"] in ("pending", "error")]

if not grading_available:
    st.error(
        "Grading is unavailable: the backend has no Anthropic API key. "
        "Add `ANTHROPIC_API_KEY=...` to `.env` and restart the server."
    )
else:
    columns = st.columns([2, 2, 3])
    regrade = columns[0].checkbox(
        "Re-grade everything", value=False,
        help="Off: only ungraded submissions are sent. On: every submission "
             "is graded again, and any approval is cleared.",
    )
    include_images = columns[1].checkbox(
        "Send figures to the grader", value=True,
        help="Lets the model judge plots. Costs more per submission.",
    )

    target_count = len(submissions) if regrade else len(ungraded)
    columns[2].caption(
        f"{target_count} submission(s) will be sent — roughly "
        f"{target_count * 15}s to {target_count * 40}s."
    )

    if st.button(f"Grade {target_count} submission(s)", type="primary",
                 disabled=target_count == 0):
        with st.spinner("Grading. This runs one model call per submission..."):
            outcome = api_client.grade(
                assignment["id"], regrade=regrade, include_images=include_images
            )

        if outcome:
            st.success(
                f"Graded {outcome['graded']}, skipped {outcome['skipped']}, "
                f"failed {outcome['failed']}."
            )
            for result in outcome["results"]:
                if result["ok"] and result.get("letter_grade"):
                    chips = flag_chips(result.get("flags") or [])
                    # Escaped: this line is rendered with unsafe_allow_html so
                    # the chips work, and the name is editable through the API.
                    name = escape(str(result["student_name"] or "(unknown)"))
                    st.markdown(
                        f"- **{name}** — "
                        f"{result['total_score']:g} "
                        f"({result['percentage']:g}%, "
                        f"{escape(str(result['letter_grade']))}) "
                        f"{chips}",
                        unsafe_allow_html=True,
                    )
                elif not result["ok"]:
                    st.markdown(
                        f"- **{result['student_name'] or '(unknown)'}** — "
                        f"{result['error']}"
                    )

            page_link("pages/review_results.py",
                         label="Next: review the results", icon=":material/fact_check:")

# ---------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------
st.divider()
st.subheader("4 · Check for similarity")
st.caption(
    "Compares every pair of submissions on normalised tokens and AST "
    "structure, so renaming variables does not hide a copy. A flag is a "
    "prompt to look, never a conclusion."
)

threshold = st.slider(
    "Flag pairs at or above", 0.3, 1.0, 0.6, 0.05,
    help="0.85+ is near-identical. Below 0.5 you will see false positives.",
)

if st.button("Run similarity scan"):
    with st.spinner("Fingerprinting and comparing..."):
        flags = api_client.scan_similarity(assignment["id"], threshold)
    if flags is not None:
        if not flags:
            st.success("No pairs above the threshold.")
        else:
            st.warning(f"{len(flags)} pair(s) flagged for review.")
            page_link("pages/review_results.py",
                         label="Review the flags", icon=":material/fact_check:")
