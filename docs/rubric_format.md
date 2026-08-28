# Rubric Format Guide

The rubric is the contract the grader is held to. It never invents
criteria of its own, and it can never award more than a criterion's
`max_points` — AutoGrade clamps the score before it reaches the database.

There are three ways to supply one.

---

## Option A — Natural language (easiest)

Paste your assignment instructions. Claude extracts the criteria and
point values, and you review the result before saving.

> Load `housing.csv` with pandas and print its shape (20 points).
> Implement closed-form OLS as `fit(X, y)` and report R² (50 points).
> Plot predicted vs actual with labelled axes (20 points).
> Write a paragraph interpreting the result (10 points).

Use **New assignment → Describe the assignment**, or the API:

```bash
POST /api/assignments/rubric/preview
{"text": "...", "total_points": 100}
```

Preview costs one API call and saves nothing, so you can iterate on the
wording until the criteria look right.

---

## Option B — Structured JSON

Full control. This is exactly what gets stored.

```json
{
  "title": "HW3 — Linear Regression",
  "criteria": [
    {
      "id": "loading",
      "name": "Data loading",
      "description": "Reads housing.csv with pandas and reports its shape.",
      "max_points": 20,
      "weight": 1.0,
      "keywords": ["read_csv", "shape"],
      "requires_output": true,
      "levels": [
        {"label": "Full",    "points": 20, "description": "Loaded and shape printed"},
        {"label": "Partial", "points": 10, "description": "Loaded, shape not reported"},
        {"label": "None",    "points": 0,  "description": "Not attempted"}
      ]
    },
    {
      "id": "model",
      "name": "Model implementation",
      "description": "Implements closed-form OLS correctly, using pinv rather than inv.",
      "max_points": 80
    }
  ],
  "grading_notes": "Strict on correctness, generous on style."
}
```

### Field reference

| Field | Required | Meaning |
|-------|----------|---------|
| `title` | no | Shown in the UI. Defaults to "Untitled rubric". |
| `criteria` | **yes** | At least 1, at most 60. |
| `grading_notes` | no | Free-text guidance passed to the grader verbatim. Use it for the things a rubric table cannot express ("this is a first-year course, reward effort"). |
| `total_points` | no | **Ignored and recomputed** from the criteria. If what you declare disagrees with the sum, the sum wins and a warning is returned. |

Per criterion:

| Field | Required | Meaning |
|-------|----------|---------|
| `name` | **yes** | Shown to the student. |
| `max_points` | **yes** | The ceiling. A score above this is clamped and flagged. |
| `id` | no | Stable key for professor overrides. Auto-generated from the name if omitted; duplicates get a numeric suffix. **Keep ids stable** — overrides are keyed by them. |
| `description` | no | What "correct" means. The single highest-leverage field: vague descriptions produce vague grading. |
| `weight` | no | Defaults to `1.0`. Must be > 0. Reserved for weighted schemes; does not affect the raw total. |
| `keywords` | no | Literal identifiers a correct solution likely contains (`pinv`, `read_csv`). Hints, not requirements. |
| `requires_output` | no | `true` means the criterion cannot be fully satisfied by code alone — the cell must have been executed. Unrun notebooks lose these points and get a `no_outputs` flag. |
| `levels` | no | Performance bands. Sorted high to low automatically. No level may exceed `max_points`. |

### Validation

A rubric is validated before it is stored, so a malformed one can never
reach the grader. Rejections you will see:

- `Criterion 'X' is missing 'max_points'`
- `Criterion 'X': max_points cannot be negative`
- `Criterion 'X': level 'Full' awards 25 points but the criterion caps at 20`
- `Rubric must contain a non-empty 'criteria' list`
- `Rubric total is 0 points`

---

## Option C — Instructor solution notebook

Upload your own solved `.ipynb` alongside the rubric. The grader receives
it as the expected result, which makes correctness judgements markedly
more reliable than rubric text alone. A student's *approach* may differ;
only a different **result** is a deduction.

**Upload & grade → Instructor reference solution**, or:

```bash
POST /api/assignments/{assignment_id}/solution   (multipart file)
```

A reference solution that fails to parse degrades grading to rubric-only
rather than blocking it.

---

## Default rubric

Create an assignment with no rubric and you get four generic criteria —
correctness, completeness, code quality, explanation — split evenly.
It works, but a rubric of your own grades far more accurately.

---

## Writing rubrics that grade well

- **Say what "correct" looks like, not just what the task is.** "Implements
  OLS" is weak; "uses `pinv` rather than `inv` and handles the singular
  case" is gradeable.
- **One criterion per thing you would actually take points off for.**
  3–8 criteria is the useful range. Fewer is too coarse for good feedback;
  more makes grading noisy.
- **Set `requires_output` honestly.** It is the mechanism that catches the
  student who wrote plausible code and never ran it.
- **Put your grading philosophy in `grading_notes`.** It is passed through
  verbatim and does real work.
- **Keep `id`s stable across edits.** Changing an id orphans every
  professor override that referenced it.

## Letter grades

Computed in Python from the percentage — never by the model, and not
configurable per rubric:

| ≥97 | ≥93 | ≥90 | ≥87 | ≥83 | ≥80 | ≥77 | ≥73 | ≥70 | ≥67 | ≥63 | ≥60 | <60 |
|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| A+  | A   | A-  | B+  | B   | B-  | C+  | C   | C-  | D+  | D   | D-  | F   |
