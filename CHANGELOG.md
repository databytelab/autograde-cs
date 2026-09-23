# Changelog

All notable changes to AutoGrade CS are recorded here. Dates are in the
`YYYY-MM-DD` format.

## v1.0.0 — 2026-09-23

First public release.

### Grading quality
- **Reads the whole submission, per question.** Building a rubric from an
  instructor solution that is laid out as numbered questions now produces one
  criterion per question (e.g. 20 questions → 20 criteria), matching your
  marking scheme, instead of collapsing into a few generic buckets.
- **Plots are actually checked.** A student's figures are sent to the model's
  vision input and judged for real (right chart, labelled axes, consistent
  with the code) — and a plot-only cell is no longer mis-reported as having no
  output.
- **Feedback written for students.** Simple, plain English aimed at beginners
  and non-native readers; praise clichés ("excellent", "great job", …) are
  banned; per-criterion feedback is kept short and the summary names the
  specific questions that lost marks.
- **Retrospective wording.** Because students cannot resubmit, feedback says
  what they *should have done* (past tense) rather than telling them to fix
  something now.
- **Fairer marking.** The grader is rigorous but no longer nitpicks correct
  work; results that differ only by a random seed, library version, or
  rounding are treated as correct.
- Uses whichever model you set in **Settings → AI providers** (OpenAI, Claude,
  or a local model); the `.env` value is only a fallback default.

### Reading submissions
- **Rewritten HTML parser** that recognises the many "notebook → HTML"
  export tools by signal rather than by one tool's exact class names, and
  refuses a parse that matches structurally but extracts nothing — so a
  notebook exported by an unfamiliar tool is read instead of silently graded
  blank.

### Review & workflow
- **One submission at a time**, with a status filter (Needs approval /
  Flagged / Approved / All), so a large class no longer slows the page down.
- **Overall feedback and Approve are at the top**; the per-criterion detail
  is collapsed by default.
- **Approving moves you to the next submission**, not back to the top.
- **Approve all** graded, unflagged submissions in one click.
- **Enter a final score directly** (out of the total) for a submission graded
  by hand, without filling in every section.
- **Manage from the dashboard:** delete an assignment or a course, and attach
  or replace a reference solution (optionally rebuilding the rubric from it).
- Canvas comments now carry only your overall feedback, not the full
  per-criterion breakdown.

### Fixes
- `Start Dev` (development launcher) no longer opens two browser tabs.

## v0.9.x-pilot

Pre-release pilot builds used within a single department.
