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


def render_submission(result: dict, *, sel_key: str | None = None,
                      advance_to: str | None = None) -> None:
    """
    The full editor for one submission - the overall feedback and approve
    button up top (where they are seen and used first), the per-criterion
    detail tucked into a collapsed panel below, and the direct final-score
    field.

    Only ever called for the single submission currently selected, so the
    page builds ~one student's worth of widgets per run instead of every
    student's - that is what keeps editing fast on a large class.

    `sel_key`/`advance_to`: after the professor approves, move the selection
    on to `advance_to` (the next submission in the queue) instead of snapping
    back to the top of the list.
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

    criteria = result.get("criteria_results") or []
    existing = result.get("professor_overrides") or {}
    total_possible = float(result["total_possible"])
    current_total = float(result["effective_score"])
    manual_active = result.get("total_override") is not None
    # A section score is locked (shown, but not editable and not counted)
    # once the grade is approved, or while a manual final score is in effect
    # - the manual score is the total then.
    sections_locked = result["finalized"] or manual_active

    def _advance_after_approve() -> None:
        # Set a pending selection rather than writing sel_key directly: the
        # selectbox is keyed by sel_key and has already been instantiated this
        # run, and Streamlit forbids mutating a live widget's state. The queue
        # fragment consumes this pending value at the top of its next run,
        # before the selectbox is built.
        if sel_key and advance_to:
            st.session_state[f"{sel_key}__pending"] = advance_to

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

    n_crit = len(criteria)

    # -----------------------------------------------------------------
    # Approved: read-only, with the summary on top and un-approve handy.
    # -----------------------------------------------------------------
    if result["finalized"]:
        top = st.columns([1, 3])
        top[0].success("Approved")
        if top[1].button("Un-approve to edit", key=f"unfin_{result['id']}"):
            if api_client.finalize(result["id"], False):
                _refresh_data()
                st.rerun()
        st.markdown("**Overall feedback**")
        st.write(result["summary_feedback"] or "_No summary feedback._")
        if manual_active:
            st.caption(
                f"Final score entered manually: {current_total:g} / "
                f"{total_possible:g} (section scores not counted)."
            )
        with st.expander(f"Per-criterion detail ({n_crit})", expanded=False):
            _render_criteria()
        with st.expander("Raw model output (audit trail)", expanded=False):
            st.json(result.get("ai_raw_output") or {})
        return

    # -----------------------------------------------------------------
    # Open: overall feedback + approve on top; detail below, collapsed.
    # -----------------------------------------------------------------
    if manual_active:
        st.info(
            f"A manual final score of **{current_total:g} / {total_possible:g}** "
            "is in effect. The section scores are kept for the record but are "
            "not counted toward the total. Clear it below to grade by section."
        )

    # One form: overall feedback and the section scores save together, and
    # nothing is sent to the server until a button is clicked - so editing
    # never reloads the page mid-keystroke.
    with st.form(f"crit_{result['id']}"):
        st.markdown("**Overall feedback**  ·  edit, then approve")
        edited_summary = st.text_area(
            "Overall feedback", value=result["summary_feedback"] or "",
            key=f"summary_{result['id']}", height=150,
            label_visibility="collapsed",
        )
        btns = st.columns([1, 1, 4])
        approve = btns[0].form_submit_button("✓ Approve", type="primary")
        save = btns[1].form_submit_button("Save")

        with st.expander(f"Per-criterion detail ({n_crit}) — open to adjust "
                         "section scores", expanded=False):
            scores = _render_criteria()
            change_note = st.text_input(
                "Reason for any score changes (optional)",
                value="", key=f"note_{result['id']}",
                disabled=sections_locked,
            )

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
            # Only the summary changed - carry it on a no-op override of the
            # first criterion. This leaves a manual total untouched: the
            # backend recomputes from effective_score, which the manual
            # score governs.
            first = criteria[0]
            api_client.override(
                result["id"],
                {first["criterion_id"]: {"new_score": first["score"],
                                         "note": ""}},
                edited_summary,
            )
        if approve:
            api_client.finalize(result["id"], True)
            _advance_after_approve()
        _refresh_data()
        st.rerun()

    # ---- Final score (enter one number, skip the sections) -----------
    with st.form(f"total_{result['id']}"):
        tcol = st.columns([3, 2])
        final_score = tcol[0].number_input(
            f"Or set a final score directly (out of {total_possible:g})",
            min_value=0.0, max_value=total_possible,
            value=current_total, step=0.5,
            key=f"total_{result['id']}_input",
        )
        set_total = tcol[1].form_submit_button("Save final score")
    if set_total:
        if api_client.set_total_override(result["id"], final_score):
            _refresh_data()
            st.rerun()
    if manual_active and st.button(
        "Clear manual score (grade by section instead)",
        key=f"cleartotal_{result['id']}",
    ):
        if api_client.set_total_override(result["id"], None):
            st.session_state.pop(f"total_{result['id']}_input", None)
            _refresh_data()
            st.rerun()

    with st.expander("Raw model output (audit trail)", expanded=False):
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
    def _label(r: dict) -> str:
        mark = "  ⚑" if r["flags"] else ""
        tick = "  ✓" if r["finalized"] else ""
        who = r.get("student_name") or "(unknown student)"
        return (f"{who} — {r['effective_score']:g}/"
                f"{r['total_possible']:g}{mark}{tick}")

    # The selectbox owns the selection through its own key; Prev / Next and
    # "advance after approve" move it with callbacks. Callbacks are the one
    # place Streamlit lets you set a widget's value safely, so this is what
    # makes the dropdown, the buttons, and approving all agree - the earlier
    # "pick from dropdown does nothing" bug came from setting the selectbox's
    # state outside a callback.
    box_key = f"rr_box_{assignment['id']}"

    # The navigation and the one editor live in a fragment so that moving
    # between students reruns only THIS block - the course/assignment pickers,
    # the stats, and the tabs above stay put instead of the whole page
    # reloading on every change.
    @st.experimental_fragment
    def _queue(filtered: list[dict]) -> None:
        ids = [r["id"] for r in filtered]
        by_id = {r["id"]: r for r in filtered}

        # Consume an "advance after approve" target left by render_submission.
        # Applied here, before the selectbox is built, so setting the widget's
        # value is legal (Streamlit forbids it once the widget exists).
        pending = st.session_state.pop(f"{box_key}__pending", None)
        if pending in ids:
            st.session_state[box_key] = pending
        if st.session_state.get(box_key) not in ids:
            st.session_state[box_key] = ids[0]
        idx = ids.index(st.session_state[box_key])

        def _step(delta: int) -> None:
            here = ids.index(st.session_state[box_key])
            st.session_state[box_key] = ids[
                max(0, min(here + delta, len(ids) - 1))
            ]

        nav = st.columns([1, 6, 1])
        nav[0].button("← Prev", disabled=idx == 0,
                      key=f"rr_prev_{assignment['id']}",
                      on_click=_step, args=(-1,))
        nav[1].selectbox(
            "Jump to a submission",
            options=ids, key=box_key,
            format_func=lambda gid: _label(by_id[gid]),
        )
        nav[2].button("Next →", disabled=idx >= len(ids) - 1,
                      key=f"rr_next_{assignment['id']}",
                      on_click=_step, args=(1,))
        st.caption(f"{idx + 1} of {len(ids)}")

        st.divider()
        # After approving, move to the next submission (or the previous one if
        # this was the last), never back to the top of the list.
        if len(ids) > 1:
            advance_to = ids[idx + 1] if idx + 1 < len(ids) else ids[idx - 1]
        else:
            advance_to = None
        render_submission(by_id[st.session_state[box_key]],
                          sel_key=box_key, advance_to=advance_to)

    _queue(filtered)

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
