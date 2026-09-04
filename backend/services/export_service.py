"""
Export grades out of AutoGrade.

Four formats, all built from the same flat row shape so the columns
never drift between them:

  CSV       - generic gradebook import
  XLSX      - one sheet of grades plus a per-criterion breakdown sheet
  Canvas CSV- the column layout Canvas' gradebook importer expects
  PDF       - one feedback sheet per student, ready to hand back

Everything returns `bytes` so the router can stream it without touching
the filesystem.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from backend.models.assignment import Assignment
from backend.models.submission import Submission


def _escape(text: Any) -> str:
    """Make arbitrary feedback text safe to drop into a PDF paragraph."""
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------
# The one canonical row shape
# ---------------------------------------------------------------------
def collect_rows(
    db: Session,
    assignment: Assignment,
    *,
    only_finalized: bool = False,
) -> list[dict[str, Any]]:
    """
    Flatten an assignment's submissions into export rows.

    Ungraded submissions are included with empty score columns - a
    professor exporting mid-run needs to see who is still missing.
    """
    submissions = (
        db.query(Submission)
        .filter(Submission.assignment_id == assignment.id)
        .order_by(Submission.student_name, Submission.original_filename)
        .all()
    )

    rows: list[dict[str, Any]] = []
    for submission in submissions:
        grade = submission.grade_result
        if only_finalized and not (grade and grade.finalized):
            continue

        row: dict[str, Any] = {
            "student_name": submission.student_name or "(unknown)",
            "student_email": submission.student_email or "",
            "student_id": submission.student_id_external or "",
            "filename": submission.original_filename,
            "status": submission.status,
            "score": float(grade.effective_score) if grade else None,
            "total_possible": float(grade.total_possible) if grade and grade.total_possible else None,
            "percentage": float(grade.percentage) if grade and grade.percentage is not None else None,
            "letter_grade": grade.letter_grade if grade else None,
            "finalized": bool(grade.finalized) if grade else False,
            "flags": ", ".join(grade.flags or []) if grade else "",
            "summary_feedback": (grade.summary_feedback or "") if grade else "",
            "graded_at": submission.graded_at.isoformat() if submission.graded_at else "",
            "submission_id": submission.id,
            "criteria": (grade.criteria_results or []) if grade else [],
            "overrides": (grade.professor_overrides or {}) if grade else {},
        }
        rows.append(row)

    return rows


_SUMMARY_COLUMNS = [
    "student_name", "student_email", "student_id", "filename", "status",
    "score", "total_possible", "percentage", "letter_grade",
    "finalized", "flags", "graded_at", "summary_feedback",
]


# Excel, LibreOffice and Google Sheets treat a cell beginning with any of
# these as a formula. Several columns here carry text that a student can
# influence - `summary_feedback` is model output written about their own
# submission - so a spreadsheet built from them is untrusted content that a
# professor then opens on their own machine.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _spreadsheet_safe(value: Any) -> Any:
    """
    Neutralise formula injection in a cell destined for a spreadsheet.

    Only strings are touched, so numeric scores (including negative ones)
    keep their type and still sum correctly. A leading apostrophe is the
    conventional escape: spreadsheet programs strip it on display and treat
    the rest as literal text.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


# ---------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------
def to_csv(rows: list[dict[str, Any]]) -> bytes:
    """Generic gradebook CSV."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=_SUMMARY_COLUMNS, extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {k: _spreadsheet_safe(row.get(k, "")) for k in _SUMMARY_COLUMNS}
        )
    # utf-8-sig so Excel opens accented names correctly on Windows.
    return buffer.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------------
# Canvas CSV
# ---------------------------------------------------------------------
def to_canvas_csv(rows: list[dict[str, Any]], assignment: Assignment) -> bytes:
    """
    Canvas gradebook import format.

    Canvas matches on the SIS/Canvas student id, so rows without one are
    still emitted but will need manual matching on import - dropping them
    silently would look like missing students.
    """
    column = f"{assignment.name} ({assignment.canvas_assignment_id or 'new'})"
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")

    writer.writerow(["Student", "ID", "SIS User ID", "SIS Login ID", column])
    # Canvas expects a "Points Possible" row directly under the header.
    writer.writerow(["    Points Possible", "", "", "",
                     assignment.total_possible_points])

    for row in rows:
        writer.writerow([
            _spreadsheet_safe(row["student_name"]),
            _spreadsheet_safe(row["student_id"]),
            _spreadsheet_safe(row["student_id"]),
            _spreadsheet_safe(row["student_email"]),
            "" if row["score"] is None else row["score"],
        ])

    return buffer.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------
def to_xlsx(rows: list[dict[str, Any]], assignment: Assignment) -> bytes:
    """
    Two sheets:
      "Grades"   - one row per student
      "Criteria" - one row per student per criterion, with the AI score,
                   any professor override, and the reasoning
    """
    summary = pd.DataFrame(
        [{k: _spreadsheet_safe(row.get(k)) for k in _SUMMARY_COLUMNS}
         for row in rows],
        columns=_SUMMARY_COLUMNS,
    )

    criteria_rows: list[dict[str, Any]] = []
    for row in rows:
        for criterion in row["criteria"]:
            override = row["overrides"].get(criterion["criterion_id"], {})
            criteria_rows.append({k: _spreadsheet_safe(v) for k, v in {
                "student_name": row["student_name"],
                "criterion": criterion.get("name"),
                "criterion_id": criterion.get("criterion_id"),
                "ai_score": criterion.get("score"),
                "max_score": criterion.get("max_score"),
                "override_score": override.get("new_score"),
                "override_note": override.get("note", ""),
                "flags": ", ".join(criterion.get("flags") or []),
                "feedback": criterion.get("feedback", ""),
                "reasoning": criterion.get("reasoning", ""),
            }.items()})

    criteria = pd.DataFrame(criteria_rows) if criteria_rows else pd.DataFrame(
        columns=["student_name", "criterion", "criterion_id", "ai_score",
                 "max_score", "override_score", "override_note", "flags",
                 "feedback", "reasoning"]
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Grades", index=False)
        criteria.to_excel(writer, sheet_name="Criteria", index=False)

        # Widen columns so the sheet is readable without manual fiddling.
        for sheet_name, frame in (("Grades", summary), ("Criteria", criteria)):
            worksheet = writer.sheets[sheet_name]
            for i, column in enumerate(frame.columns, start=1):
                longest = max(
                    [len(str(column))]
                    + [len(str(v)) for v in frame[column].head(200).tolist()]
                )
                worksheet.column_dimensions[
                    worksheet.cell(row=1, column=i).column_letter
                ].width = min(max(longest + 2, 10), 60)

    return buffer.getvalue()


# ---------------------------------------------------------------------
# PDF feedback sheets
# ---------------------------------------------------------------------
def to_pdf(
    rows: list[dict[str, Any]],
    assignment: Assignment,
    course_name: str = "",
) -> bytes:
    """One page (or more) of feedback per student, ready to hand back."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        title=f"{assignment.name} - feedback",
    )

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=9.5, leading=13,
        alignment=TA_LEFT, spaceAfter=4,
    )
    small = ParagraphStyle("Small", parent=body, fontSize=8, textColor=colors.grey)

    story: list[Any] = []

    if not rows:
        story.append(Paragraph("No grades to export.", styles["Title"]))
        doc.build(story)
        return buffer.getvalue()

    for position, row in enumerate(rows):
        if position:
            story.append(PageBreak())

        story.append(Paragraph(_escape(assignment.name), styles["Title"]))
        if course_name:
            story.append(Paragraph(_escape(course_name), small))
        story.append(Spacer(1, 10))

        score = row["score"]
        possible = row["total_possible"]
        headline = (
            f"{score:g} / {possible:g}  ({row['percentage']:g}%  "
            f"{row['letter_grade']})"
            if score is not None and possible
            else "Not yet graded"
        )
        story.append(Paragraph(f"<b>{_escape(row['student_name'])}</b>", styles["Heading2"]))
        story.append(Paragraph(headline, styles["Heading3"]))
        story.append(Paragraph(f"File: {_escape(row['filename'])}", small))
        story.append(Spacer(1, 12))

        if row["summary_feedback"]:
            story.append(Paragraph("<b>Overall</b>", styles["Heading4"]))
            story.append(Paragraph(_escape(row["summary_feedback"]), body))
            story.append(Spacer(1, 10))

        if row["criteria"]:
            story.append(Paragraph("<b>Breakdown</b>", styles["Heading4"]))
            data: list[list[Any]] = [["Criterion", "Score", "Feedback"]]
            for criterion in row["criteria"]:
                override = row["overrides"].get(criterion["criterion_id"], {})
                awarded = override.get("new_score", criterion.get("score"))
                cell_score = f"{float(awarded):g} / {float(criterion.get('max_score', 0)):g}"
                if override:
                    cell_score += "\n(adjusted)"
                data.append([
                    Paragraph(_escape(criterion.get("name")), body),
                    Paragraph(cell_score, body),
                    Paragraph(_escape(criterion.get("feedback")), body),
                ])

            table = Table(data, colWidths=[1.6 * inch, 0.9 * inch, 4.5 * inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D3DF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(table)

        if row["flags"]:
            story.append(Spacer(1, 10))
            story.append(Paragraph(
                f"<b>Flagged for review:</b> {_escape(row['flags'])}", small
            ))

        story.append(Spacer(1, 14))
        story.append(Paragraph(
            f"Generated by AutoGrade CS on "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')}. "
            f"AI-assisted grade reviewed by your instructor.",
            small,
        ))

    doc.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------
FORMATS = {
    "csv":        ("text/csv", "csv"),
    "canvas_csv": ("text/csv", "csv"),
    "xlsx":       ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "pdf":        ("application/pdf", "pdf"),
}


def export(
    db: Session,
    assignment: Assignment,
    fmt: str,
    *,
    only_finalized: bool = False,
    course_name: str = "",
) -> tuple[bytes, str, str]:
    """
    Build an export.

    Returns (payload, media_type, filename).
    Raises ValueError for an unknown format.
    """
    if fmt not in FORMATS:
        raise ValueError(
            f"Unknown export format '{fmt}'. Choose one of: "
            f"{', '.join(sorted(FORMATS))}"
        )

    rows = collect_rows(db, assignment, only_finalized=only_finalized)
    media_type, extension = FORMATS[fmt]

    if fmt == "csv":
        payload = to_csv(rows)
    elif fmt == "canvas_csv":
        payload = to_canvas_csv(rows, assignment)
    elif fmt == "xlsx":
        payload = to_xlsx(rows, assignment)
    else:
        payload = to_pdf(rows, assignment, course_name=course_name)

    safe_name = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in assignment.name
    )[:60] or "assignment"
    suffix = "_canvas" if fmt == "canvas_csv" else ""
    filename = f"{safe_name}{suffix}_grades.{extension}"

    return payload, media_type, filename
