"""Read the grades, adjust them, approve them, and work the similarity queue."""
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
    flag_chips,
    grade_badge,
    page_setup,
    require_auth,
    stats_row,
)

page_setup("Review results")
require_auth()

st.title("Review results")

course = course_selector()
if course is None:
    st.stop()

assignment = assignment_selector(course["id"])
if assignment is None:
    st.stop()

stats = api_client.get_stats(assignment["id"])
if stats:
    stats_row(stats)

grades_tab, similarity_tab = st.tabs(["Grades", f"Similarity ({stats['flagged'] if stats else 0})"])

# ---------------------------------------------------------------------
# Grades
# ---------------------------------------------------------------------
with grades_tab:
    columns = st.columns([2, 2, 4])
    flagged_only = columns[0].checkbox(
        "Only flagged", value=False,
        help="Submissions the grader raised an integrity or quality flag on. "
             "This is the queue worth reading first.",
    )
    hide_finalized = columns[1].checkbox("Hide approved", value=False)

    results = api_client.list_results(assignment["id"], flagged_only=flagged_only)
    if results is None:
        st.stop()

    if hide_finalized:
        results = [r for r in results if not r["finalized"]]

    if not results:
        st.info("Nothing to review here.")
        st.stop()

    st.caption(f"{len(results)} result(s)")

    for result in results:
        name = result.get("student_name") or "(unknown student)"
        badge = grade_badge(result["letter_grade"], result["percentage"])
        approved = "  ·  approved" if result["finalized"] else ""

        with st.expander(
            f"{name} — {result['effective_score']:g}/{result['total_possible']:g}"
            f"{approved}",
            expanded=False,
        ):
            header = st.columns([3, 2])
            header[0].markdown(badge, unsafe_allow_html=True)
            header[0].caption(f"File: {result['original_filename']}")
            if result["flags"]:
                header[1].markdown(flag_chips(result["flags"]),
                                   unsafe_allow_html=True)

            if result["summary_feedback"]:
                st.markdown("**Overall feedback**")
                st.write(result["summary_feedback"])

            st.markdown("**Per-criterion**")
            overrides: dict[str, dict] = {}
            existing = result.get("professor_overrides") or {}

            for criterion in result.get("criteria_results") or []:
                cid = criterion["criterion_id"]
                max_score = float(criterion["max_score"])
                # The backend clamps scores to the criterion maximum, but a
                # hand-edited or legacy row could still be out of range -
                # and st.number_input raises if value > max_value, which
                # would take down the whole review page.
                current = min(
                    float(existing.get(cid, {}).get("new_score",
                                                    criterion["score"])),
                    max_score,
                )

                with st.container(border=True):
                    row = st.columns([3, 1.4, 1.4])
                    row[0].markdown(f"**{criterion['name']}**")

                    row[1].markdown(
                        f"AI: `{criterion['score']:g} / {max_score:g}`"
                    )
                    new_score = row[2].number_input(
                        "Your score",
                        min_value=0.0,
                        max_value=max_score,
                        value=current,
                        step=0.5,
                        key=f"score_{result['id']}_{cid}",
                        disabled=result["finalized"],
                        label_visibility="collapsed",
                    )

                    if criterion["feedback"]:
                        st.caption(f"**To the student:** {criterion['feedback']}")
                    if criterion["reasoning"]:
                        st.caption(f"**Grader's reasoning:** {criterion['reasoning']}")
                    if criterion["flags"]:
                        st.markdown(flag_chips(criterion["flags"]),
                                    unsafe_allow_html=True)

                    if abs(new_score - float(criterion["score"])) > 0.001:
                        note = st.text_input(
                            "Why did you change this?",
                            value=existing.get(cid, {}).get("note", ""),
                            key=f"note_{result['id']}_{cid}",
                            disabled=result["finalized"],
                        )
                        overrides[cid] = {"new_score": new_score, "note": note}

            edited_summary = st.text_area(
                "Summary feedback (edit before approving if you like)",
                value=result["summary_feedback"] or "",
                key=f"summary_{result['id']}",
                disabled=result["finalized"],
            )

            actions = st.columns([2, 2, 4])

            if result["finalized"]:
                actions[0].success("Approved")
                if actions[1].button("Un-approve", key=f"unfin_{result['id']}"):
                    if api_client.finalize(result["id"], False):
                        st.rerun()
            else:
                save_disabled = not overrides and edited_summary == (
                    result["summary_feedback"] or ""
                )
                if actions[0].button(
                    "Save changes", key=f"save_{result['id']}",
                    disabled=save_disabled, type="secondary",
                ):
                    if overrides:
                        updated = api_client.override(
                            result["id"], overrides, edited_summary
                        )
                    else:
                        # Only the summary changed - send a no-op override on
                        # the first criterion so the text is persisted.
                        first = result["criteria_results"][0]
                        updated = api_client.override(
                            result["id"],
                            {first["criterion_id"]: {
                                "new_score": first["score"], "note": ""}},
                            edited_summary,
                        )
                    if updated:
                        st.success("Saved.")
                        st.rerun()

                if actions[1].button(
                    "Approve", key=f"fin_{result['id']}", type="primary"
                ):
                    if overrides:
                        api_client.override(result["id"], overrides, edited_summary)
                    if api_client.finalize(result["id"], True):
                        st.rerun()

            # A toggle rather than an expander: this block is already
            # inside one, and Streamlit will not nest them.
            if st.toggle("Show the raw model output (audit trail)",
                         key=f"raw_{result['id']}"):
                st.json(result.get("ai_raw_output") or {})

# ---------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------
with similarity_tab:
    st.caption(
        "Flags are evidence to look at, not a verdict. Two students who "
        "worked from the same lecture example will legitimately look alike."
    )

    flags = api_client.list_similarity(assignment["id"])
    if flags is None:
        st.stop()

    if not flags:
        st.info(
            "No similarity flags. Run a scan from the **Upload & grade** page."
        )
    else:
        for flag in flags:
            severity = flag["severity"]
            reviewed = "  ·  reviewed" if flag["reviewed"] else ""

            with st.expander(
                f"[{severity}]  {flag['student_a_name'] or '?'} and "
                f"{flag['student_b_name'] or '?'} — "
                f"{flag['similarity_score']:.0%}{reviewed}"
            ):
                columns = st.columns(3)
                columns[0].metric("Similarity", f"{flag['similarity_score']:.0%}")
                columns[1].metric("Severity", flag["severity"])
                columns[2].metric("Method", flag["method"])

                note = st.text_area(
                    "Your note", value=flag["professor_note"] or "",
                    key=f"flagnote_{flag['id']}",
                    placeholder="What you found, who you spoke to, what you decided.",
                )
                buttons = st.columns([2, 2, 4])
                if buttons[0].button("Mark reviewed", key=f"rev_{flag['id']}"):
                    if api_client.review_similarity(flag["id"], True, note):
                        st.rerun()
                if flag["reviewed"] and buttons[1].button(
                    "Reopen", key=f"reopen_{flag['id']}"
                ):
                    if api_client.review_similarity(flag["id"], False, note):
                        st.rerun()
