"""Download grades, or push them back into Canvas."""
from __future__ import annotations

import streamlit as st

import sys
from pathlib import Path

# Streamlit puts only this file's directory on sys.path - see app.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend_streamlit.components import api_client
from frontend_streamlit.components.ui import (
    assignment_selector,
    course_selector,
    page_link,
    page_setup,
    require_auth,
    stats_row,
)

page_setup("Export")
require_auth()

st.title("Export")

course = course_selector()
if course is None:
    st.stop()

assignment = assignment_selector(course["id"])
if assignment is None:
    st.stop()

stats = api_client.get_stats(assignment["id"])
if stats:
    stats_row(stats)
    if stats["graded"] and stats["finalized"] < stats["graded"]:
        st.info(
            f"{stats['graded'] - stats['finalized']} graded submission(s) are "
            f"not approved yet. Approve them on the **Review results** page "
            f"before handing anything to students."
        )

st.divider()

# ---------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------
st.subheader("Download")

only_finalized = st.checkbox(
    "Only approved grades", value=False,
    help="On: skip anything you have not signed off. Recommended for "
         "anything a student or registrar will see.",
)

FORMATS = [
    ("csv", "CSV", "Generic gradebook import - one row per student."),
    ("xlsx", "Excel", "Two sheets: grades, plus a per-criterion breakdown "
                      "with the AI score, your override, and the reasoning."),
    ("pdf", "PDF feedback", "One feedback sheet per student, ready to hand "
                            "back."),
    ("canvas_csv", "Canvas CSV", "The column layout the Canvas gradebook "
                                 "importer expects."),
]

# The four blurbs are not the same length, so left to themselves the columns
# put their buttons at four different heights (Excel wraps to three lines and
# drops below the rest). Reserving three lines for every blurb lines the
# buttons up without padding the copy out with filler.
st.markdown(
    """
    <style>
    .ag-fmt__title{font-size:1.45rem; font-weight:700; line-height:1.3;
      margin:0 0 .45rem}
    .ag-fmt__blurb{font-size:.95rem; line-height:1.55; color:#6B655B;
      margin:0 0 .75rem; min-height:4.65em}
    @media (max-width:640px){ .ag-fmt__blurb{min-height:0} }
    </style>
    """,
    unsafe_allow_html=True,
)

columns = st.columns(len(FORMATS))
for column, (fmt, label, blurb) in zip(columns, FORMATS):
    with column:
        st.markdown(
            f'<div class="ag-fmt__title">{label}</div>'
            f'<div class="ag-fmt__blurb">{blurb}</div>',
            unsafe_allow_html=True,
        )
        if st.button(f"Build {label}", key=f"build_{fmt}",
                     use_container_width=True):
            with st.spinner(f"Building the {label} file..."):
                outcome = api_client.export_bytes(
                    assignment["id"], fmt, only_finalized
                )
            if outcome:
                content, filename = outcome
                st.session_state[f"export_{fmt}"] = (content, filename)

        stored = st.session_state.get(f"export_{fmt}")
        if stored:
            content, filename = stored
            st.download_button(
                f"Download {filename}",
                data=content,
                file_name=filename,
                key=f"dl_{fmt}",
                use_container_width=True,
                type="primary",
            )

# ---------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------
st.divider()
st.subheader("Canvas")

canvas = api_client.canvas_status() or {}
if not canvas.get("configured"):
    st.info(
        "Canvas is not connected. Add your own Canvas account under "
        "**Settings → Canvas** — it takes a minute and the token stays "
        "yours. The **Canvas CSV** download above works without it."
    )
    page_link("pages/settings_canvas.py", "Connect Canvas",
              ":material/school:")
else:
    if canvas.get("source") == "server":
        st.caption(f"Connected to {canvas.get('base_url')} using this "
                   "server's Canvas account. To push into your own courses, "
                   "connect your account under **Settings → Canvas**.")
    else:
        st.caption(f"Connected to {canvas.get('base_url')}")

    if not course.get("canvas_course_id"):
        st.warning(
            "This course has no Canvas course ID. Add one when you create "
            "the course, or edit it via the API."
        )
    elif not assignment.get("canvas_assignment_id"):
        st.warning("This assignment has no Canvas assignment ID.")
    else:
        step_one, step_two = st.columns(2)

        with step_one:
            st.markdown("**1 · Match students to the roster**")
            st.caption(
                "Fills in each submission's Canvas user ID. Anything that "
                "cannot be matched confidently is listed rather than guessed."
            )
            if st.button("Sync roster", use_container_width=True):
                with st.spinner("Fetching the roster..."):
                    outcome = api_client.canvas_sync_roster(assignment["id"])
                if outcome:
                    st.success(
                        f"Matched {outcome['matched']} of "
                        f"{outcome['roster_size']} roster entries."
                    )
                    if outcome["unmatched"]:
                        st.warning(f"{len(outcome['unmatched'])} unmatched:")
                        for entry in outcome["unmatched"]:
                            st.markdown(
                                f"- {entry['student_name'] or '(unknown)'} "
                                f"(`{entry['filename']}`)"
                            )

        with step_two:
            st.markdown("**2 · Push grades**")
            st.caption(
                "Writes scores and your summary feedback into the Canvas "
                "gradebook. This overwrites whatever is there."
            )
            push_finalized = st.checkbox(
                "Approved grades only", value=True, key="push_finalized"
            )
            if not push_finalized:
                st.error(
                    "You are about to push grades you have not reviewed."
                )
            if st.button("Push to Canvas", type="primary",
                         use_container_width=True):
                with st.spinner("Pushing..."):
                    outcome = api_client.canvas_push_grades(
                        assignment["id"], push_finalized
                    )
                if outcome:
                    st.success(f"Submitted {outcome.get('submitted', 0)} grade(s).")
                    if outcome.get("skipped"):
                        st.warning(f"{len(outcome['skipped'])} skipped:")
                        for entry in outcome["skipped"]:
                            st.markdown(
                                f"- {entry['student_name'] or '(unknown)'} — "
                                f"{entry['reason']}"
                            )
