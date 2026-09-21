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


# ---------------------------------------------------------------------
# Reading the grades is the slow part - one round-trip per submission
# list, plus the similarity list, plus the stats. Streamlit re-runs the
# whole script on every widget interaction, so without this the page
# re-fetched everything from the API each time a score was nudged, which
# is what made editing feel like it "kept browsing". We cache each fetch
# in session state, keyed by a nonce that only changes when we actually
# save something - so editing is served from memory, and a save (or an
# assignment switch) still gets fresh data.
# ---------------------------------------------------------------------
def _refresh_data() -> None:
    """Invalidate the cache so the next read re-fetches from the API."""
    st.session_state["_rr_nonce"] = st.session_state.get("_rr_nonce", 0) + 1


def _cached(key: tuple, loader):
    nonce = st.session_state.get("_rr_nonce", 0)
    cache = st.session_state.setdefault("_rr_cache", {})
    full_key = (nonce,) + key
    if full_key not in cache:
        # Drop entries from a previous nonce so the cache can't grow without
        # bound as the professor saves their way through the queue.
        for stale in [k for k in cache if k[0] != nonce]:
            del cache[stale]
        value = loader()
        if value is None:            # an API error - don't cache it, retry
            return None
        cache[full_key] = value
    return cache[full_key]


def render_submission(result: dict) -> None:
    """
    The full editor for one submission - score inputs, the direct final
    score, feedback, and the approve/save buttons.

    Only ever called for the single submission currently selected, so the
    page builds ~one student's worth of widgets per run instead of every
    student's. That is what keeps editing fast on a large class: Streamlit
    re-runs the whole script on each interaction, and rendering all 40+
    editors every time was the real cost.
    """
    name = result.get("student_name") or "(unknown student)"
    st.subheader(name)

    header = st.columns([3, 2])
    header[0].markdown(
        grade_badge(result["letter_grade"], result["percentage"]),
        unsafe_allow_html=True,
    )
    header[0].caption(f"File: {result['original_filename']}")
    if result["flags"]:
        header[1].markdown(flag_chips(result["flags"]), unsafe_allow_html=True)

    if result["summary_feedback"]:
        st.markdown("**Overall feedback**")
        st.write(result["summary_feedback"])

    criteria = result.get("criteria_results") or []
    existing = result.get("professor_overrides") or {}
    total_possible = float(result["total_possible"])
    current_total = float(result["effective_score"])
    manual_active = result.get("total_override") is not None
    # A section score is locked (shown, but not editable and not counted)
    # once the grade is approved, or while a manual final score is in effect
    # - the manual score is the total then.
    sections_locked = result["finalized"] or manual_active

    # ---- Final score (enter one number, skip the sections) -----------
    if not result["finalized"] or manual_active:
        st.markdown("**Final score**")
    if manual_active:
        st.info(
            f"A manual final score of **{current_total:g} / "
            f"{total_possible:g}** is in effect. The section scores below are "
            "kept for the record but are not counted toward the total. Clear "
            "it to grade by section instead."
        )
    if not result["finalized"]:
        with st.form(f"total_{result['id']}"):
            tcol = st.columns([3, 2])
            final_score = tcol[0].number_input(
                f"Final score (out of {total_possible:g})",
                min_value=0.0,
                max_value=total_possible,
                value=current_total,
                step=0.5,
                key=f"total_{result['id']}_input",
            )
            set_total = tcol[1].form_submit_button("Save final score",
                                                   type="primary")
        if set_total:
            if api_client.set_total_override(result["id"], final_score):
                _refresh_data()
                st.rerun()
        if manual_active and st.button(
            "Clear manual score (grade by section instead)",
            key=f"cleartotal_{result['id']}",
        ):
            if api_client.set_total_override(result["id"], None):
                # Drop the field's kept value so it re-defaults to the
                # criterion-based total rather than the number just cleared.
                st.session_state.pop(f"total_{result['id']}_input", None)
                _refresh_data()
                st.rerun()

    st.divider()

    # ---- Per-criterion ----------------------------------------------
    st.markdown("**Per-criterion**")

    def _render_criteria() -> dict[str, float]:
        """Draw each criterion's score input; return {cid: value}."""
        values: dict[str, float] = {}
        for criterion in criteria:
            cid = criterion["criterion_id"]
            max_score = float(criterion["max_score"])
            # The backend clamps scores to the criterion maximum, but a
            # hand-edited or legacy row could still be out of range, and
            # st.number_input raises if value > max_value, which would take
            # down the whole review page.
            current = min(
                float(existing.get(cid, {}).get("new_score", criterion["score"])),
                max_score,
            )
            with st.container(border=True):
                row = st.columns([3, 1.4, 1.4])
                row[0].markdown(f"**{criterion['name']}**")
                row[1].markdown(f"AI: `{criterion['score']:g} / {max_score:g}`")
                values[cid] = row[2].number_input(
                    "Your score",
                    min_value=0.0,
                    max_value=max_score,
                    value=current,
                    step=0.5,
                    key=f"score_{result['id']}_{cid}",
                    disabled=sections_locked,
                    label_visibility="collapsed",
                )
                if criterion["feedback"]:
                    st.caption(f"**To the student:** {criterion['feedback']}")
                if criterion["reasoning"]:
                    st.caption(f"**Grader's reasoning:** {criterion['reasoning']}")
                if criterion["flags"]:
                    st.markdown(flag_chips(criterion["flags"]),
                                unsafe_allow_html=True)
        return values

    if result["finalized"]:
        _render_criteria()
        actions = st.columns([2, 2, 4])
        actions[0].success("Approved")
        if actions[1].button("Un-approve", key=f"unfin_{result['id']}"):
            if api_client.finalize(result["id"], False):
                _refresh_data()
                st.rerun()
    else:
        # One form: nothing is sent to the server until the professor clicks
        # a button, so editing a score no longer reloads the page.
        with st.form(f"crit_{result['id']}"):
            scores = _render_criteria()
            change_note = st.text_input(
                "Reason for any score changes (optional)",
                value="",
                key=f"note_{result['id']}",
                disabled=sections_locked,
            )
            edited_summary = st.text_area(
                "Summary feedback (edit before approving if you like)",
                value=result["summary_feedback"] or "",
                key=f"summary_{result['id']}",
            )
            btns = st.columns([2, 2, 4])
            save = btns[0].form_submit_button("Save changes")
            approve = btns[1].form_submit_button("Approve", type="primary")

        if save or approve:
            overrides: dict[str, dict] = {}
            if not sections_locked:
                for criterion in criteria:
                    cid = criterion["criterion_id"]
                    if abs(scores[cid] - float(criterion["score"])) > 0.001:
                        overrides[cid] = {"new_score": scores[cid],
                                          "note": change_note}
            summary_changed = edited_summary != (result["summary_feedback"] or "")
            if overrides:
                api_client.override(result["id"], overrides, edited_summary)
            elif summary_changed and criteria:
                # Only the summary changed - carry it on a no-op override of
                # the first criterion. This leaves a manual total untouched:
                # the backend recomputes from effective_score, which the
                # manual score governs.
                first = criteria[0]
                api_client.override(
                    result["id"],
                    {first["criterion_id"]: {"new_score": first["score"],
                                             "note": ""}},
                    edited_summary,
                )
            if approve:
                api_client.finalize(result["id"], True)
            _refresh_data()
            st.rerun()

    with st.expander("Show the raw model output (audit trail)"):
        st.json(result.get("ai_raw_output") or {})


course = course_selector()
if course is None:
    st.stop()

assignment = assignment_selector(course["id"])
if assignment is None:
    st.stop()

stats = _cached(("stats", assignment["id"]),
                lambda: api_client.get_stats(assignment["id"]))
if stats:
    stats_row(stats)

grades_tab, similarity_tab = st.tabs(["Grades", f"Similarity ({stats['flagged'] if stats else 0})"])

# ---------------------------------------------------------------------
# Grades
# ---------------------------------------------------------------------
with grades_tab:
    results = _cached(
        ("results", assignment["id"]),
        lambda: api_client.list_results(assignment["id"]),
    )
    if results is None:
        st.stop()

    # ---- Status filter ------------------------------------------------
    STATUS = ["Needs approval", "Flagged", "Approved", "All"]
    choice = st.radio("Show", STATUS, horizontal=True,
                      key=f"rr_filter_{assignment['id']}")

    def _matches(r: dict) -> bool:
        if choice == "Needs approval":
            return not r["finalized"]
        if choice == "Flagged":
            return bool(r["flags"])
        if choice == "Approved":
            return bool(r["finalized"])
        return True

    filtered = [r for r in results if _matches(r)]

    # ---- Approve all (graded, unflagged, not yet approved) ------------
    approvable = [r for r in results if not r["finalized"] and not r["flags"]]
    bar = st.columns([3, 2])
    bar[0].caption(
        f"{len(filtered)} shown  ·  {len(approvable)} graded & unflagged "
        "awaiting approval"
    )
    if approvable:
        confirm_key = f"rr_confirm_all_{assignment['id']}"
        if not st.session_state.get(confirm_key, False):
            if bar[1].button(f"Approve all {len(approvable)} unflagged",
                             key=f"rr_approveall_{assignment['id']}"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            st.warning(
                f"Approve all {len(approvable)} graded, unflagged submissions? "
                "Flagged ones are left for you to review individually."
            )
            yes, no = st.columns([1, 1])
            if yes.button("Yes, approve them", type="primary",
                          key=f"rr_approveall_yes_{assignment['id']}"):
                outcome = api_client.finalize_all(assignment["id"],
                                                  skip_flagged=True)
                st.session_state[confirm_key] = False
                if outcome is not None:
                    _refresh_data()
                    st.success(f"Approved {outcome.get('finalized', 0)}.")
                    st.rerun()
            if no.button("Cancel", key=f"rr_approveall_no_{assignment['id']}"):
                st.session_state[confirm_key] = False
                st.rerun()

    if not filtered:
        st.info("Nothing to review here.")
        st.stop()

    # ---- One submission at a time ------------------------------------
    # Track the current submission by id (not position) so it survives
    # filtering and approving; when it drops out of the list, fall through
    # to the first still-showing one.
    def _label(r: dict) -> str:
        mark = "  ⚑" if r["flags"] else ""
        tick = "  ✓" if r["finalized"] else ""
        who = r.get("student_name") or "(unknown student)"
        return (f"{who} — {r['effective_score']:g}/"
                f"{r['total_possible']:g}{mark}{tick}")

    ids = [r["id"] for r in filtered]
    sel_key = f"rr_selected_{assignment['id']}"
    current_id = st.session_state.get(sel_key)
    if current_id not in ids:
        current_id = ids[0]
    idx = ids.index(current_id)

    nav = st.columns([1, 6, 1])
    if nav[0].button("← Prev", disabled=idx == 0,
                     key=f"rr_prev_{assignment['id']}"):
        st.session_state[sel_key] = ids[idx - 1]
        st.rerun()
    # No key on purpose: a keyed selectbox keeps its own stored value, which
    # then fights the Prev/Next buttons (they update the selection, but the
    # box's stored value snaps it back). Driving it by `index` alone keeps the
    # buttons and the dropdown in agreement.
    picked = nav[1].selectbox(
        f"Submission ({idx + 1} of {len(filtered)})",
        options=ids, index=idx,
        format_func=lambda gid: _label(next(r for r in filtered if r["id"] == gid)),
    )
    if nav[2].button("Next →", disabled=idx >= len(filtered) - 1,
                     key=f"rr_next_{assignment['id']}"):
        st.session_state[sel_key] = ids[idx + 1]
        st.rerun()
    if picked != current_id:
        st.session_state[sel_key] = picked
        st.rerun()

    st.divider()
    render_submission(next(r for r in filtered if r["id"] == current_id))

# ---------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------
with similarity_tab:
    st.caption(
        "Flags are evidence to look at, not a verdict. Two students who "
        "worked from the same lecture example will legitimately look alike."
    )

    # Cached like the grades list: st.tabs renders both tabs on every run,
    # so without this the similarity list was re-fetched on every score edit
    # too, adding to the lag.
    flags = _cached(("similarity", assignment["id"]),
                    lambda: api_client.list_similarity(assignment["id"]))
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
                        _refresh_data()
                        st.rerun()
                if flag["reviewed"] and buttons[1].button(
                    "Reopen", key=f"reopen_{flag['id']}"
                ):
                    if api_client.review_similarity(flag["id"], False, note):
                        _refresh_data()
                        st.rerun()
