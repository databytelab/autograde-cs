"""
End-to-end grading smoke test.

Grade ONE real submission with whatever provider is configured in .env, and
print the result. This is the fastest way to confirm a provider (OpenAI,
Anthropic, or a local Qwen) is wired up and actually working - it makes a
real API call, so it needs a configured key (or a running local server).

Examples
--------
Grade the bundled Lab 2 example against a generated default rubric, using the
instructor file as the reference solution:

    python scripts/smoke_test.py \
        --student Lab2_Tasks_student_submission.html \
        --solution Lab2_DT_Solution.html

Grade against your own rubric JSON (see docs/rubric_format.md):

    python scripts/smoke_test.py --student sub.ipynb --rubric rubric.json

Switch providers by editing LLM_PROVIDER in .env first (openai / anthropic /
local) - this script always uses whatever is active.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.ai.grader import GradingError, grade_submission  # noqa: E402
from backend.ai.providers import get_provider  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.parsers import ParseError, parse_submission  # noqa: E402
from backend.services.rubric_service import (  # noqa: E402
    RubricError,
    build_default_rubric,
    validate_rubric,
)

BAR = "-" * 68


def _load_rubric(path: str | None, points: float) -> dict:
    if not path:
        print(f"No rubric given - generating a default {points:g}-point rubric.")
        return build_default_rubric(points)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_rubric(data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--student", required=True, help="Student submission file")
    ap.add_argument("--solution", help="Instructor reference solution (optional)")
    ap.add_argument("--rubric", help="Rubric JSON file (optional)")
    ap.add_argument("--points", type=float, default=100.0,
                    help="Total points for the generated default rubric")
    ap.add_argument("--name", default="Smoke test assignment")
    ap.add_argument("--no-images", action="store_true",
                    help="Do not send figures (use for text-only local models)")
    args = ap.parse_args()

    provider = get_provider()
    print(BAR)
    print(f"Provider   {provider.name}")
    print(f"Model      {provider._model_for('grading')}")  # noqa: SLF001
    print(f"Configured {settings.grading_configured()}")
    print(BAR)

    if not settings.grading_configured():
        print("\nX The active provider is not configured.")
        print("  Set the right key/URL in .env for LLM_PROVIDER="
              f"{settings.active_provider()} and try again.")
        return 2

    try:
        student = parse_submission(args.student)
    except ParseError as exc:
        print(f"\nX Could not parse the student file: {exc}")
        return 2

    solution = None
    if args.solution:
        try:
            solution = parse_submission(args.solution)
        except ParseError as exc:
            print(f"! Could not parse the solution ({exc}); grading without it.")

    try:
        rubric = _load_rubric(args.rubric, args.points)
    except (RubricError, json.JSONDecodeError, OSError) as exc:
        print(f"\nX Rubric problem: {exc}")
        return 2

    print(f"\nGrading '{Path(args.student).name}' "
          f"against {len(rubric['criteria'])} criteria "
          f"({rubric['total_points']:g} points)...\n")

    try:
        result = grade_submission(
            parsed=student,
            rubric=rubric,
            assignment_name=args.name,
            expected_solution=solution,
            include_images=not args.no_images,
        )
    except GradingError as exc:
        print(f"X Grading failed: {exc}")
        return 1

    print(BAR)
    print(f"SCORE   {result['total_score']:g} / {result['total_possible']:g}"
          f"   ({result['percentage']:g}%)   grade {result['letter_grade']}")
    if result["flags"]:
        print(f"FLAGS   {', '.join(result['flags'])}")
    print(BAR)
    for c in result["criteria_results"]:
        line = f"  {c['name']:<28} {c['score']:>5g} / {c['max_score']:<5g}"
        if c["flags"]:
            line += f"  [{', '.join(c['flags'])}]"
        print(line)
        if c.get("feedback"):
            print(f"      -> {c['feedback']}")
    print(BAR)
    print("Summary:", result["summary_feedback"])
    usage = result.get("usage", {})
    print(f"\nTokens  in={usage.get('input_tokens')} "
          f"out={usage.get('output_tokens')}  model={usage.get('model')}")
    print("\nOK: End-to-end grading works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
