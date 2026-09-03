"""
Measure grader consistency and cost.

The question this answers: *if I grade the same submission five times,
how much does the score move?* Run it before trusting AutoGrade with a
real class, and again whenever you change a rubric or a prompt.

    python scripts/benchmark_grader.py --runs 5
    python scripts/benchmark_grader.py --runs 3 --file path/to/submission.ipynb
    python scripts/benchmark_grader.py --dry-run     # cost estimate only

Needs a real ANTHROPIC_API_KEY. Every run is a paid API call.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.ai.grader import GradingError, grade_submission  # noqa: E402
from backend.ai.providers import get_provider  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.parsers import ParseError, parse_submission  # noqa: E402
from backend.services.rubric_service import validate_rubric  # noqa: E402

DEFAULT_FILE = PROJECT_ROOT / "tests" / "sample_submissions" / "good_submission.ipynb"

# claude-opus-5, USD per million tokens.
INPUT_PER_MTOK = 5.00
OUTPUT_PER_MTOK = 25.00
CACHE_READ_PER_MTOK = 0.50

BENCHMARK_RUBRIC = validate_rubric({
    "title": "Benchmark rubric",
    "criteria": [
        {"id": "loading", "name": "Data loading",
         "description": "Reads the data file and reports its shape.",
         "max_points": 20, "requires_output": True},
        {"id": "model", "name": "Model implementation",
         "description": "Implements the requested model correctly.",
         "max_points": 40},
        {"id": "evaluation", "name": "Evaluation",
         "description": "Reports an appropriate metric and states its value.",
         "max_points": 20, "requires_output": True},
        {"id": "writeup", "name": "Write-up",
         "description": "Explains in prose what the result means.",
         "max_points": 20},
    ],
    "grading_notes": "Strict on correctness, generous on style.",
})


def estimate_cost(usage: dict) -> float:
    return (
        usage.get("input_tokens", 0) / 1e6 * INPUT_PER_MTOK
        + usage.get("output_tokens", 0) / 1e6 * OUTPUT_PER_MTOK
        + usage.get("cache_read_input_tokens", 0) / 1e6 * CACHE_READ_PER_MTOK
    )


def spread(label: str, values: list[float], unit: str = "") -> None:
    if not values:
        return
    low, high = min(values), max(values)
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    print(f"  {label:22} mean {mean:7.2f}{unit}   "
          f"sd {stdev:5.2f}   range {low:g}-{high:g}{unit}   "
          f"spread {high - low:g}{unit}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5,
                        help="How many times to grade the same file (default 5).")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE,
                        help="Submission to grade repeatedly.")
    parser.add_argument("--no-images", action="store_true",
                        help="Skip figures - cheaper, and isolates text grading.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and report size only; make no API calls.")
    args = parser.parse_args()

    try:
        parsed = parse_submission(args.file)
    except ParseError as exc:
        print(f"Could not parse {args.file}: {exc}")
        sys.exit(1)

    stats = parsed["stats"]
    print(f"File      {args.file.name}")
    print(f"Type      {parsed['file_type']}")
    print(f"Content   {stats['n_code_cells']} code cells, "
          f"{stats['n_markdown_cells']} markdown, {stats['loc']} LOC, "
          f"{stats['n_images']} figure(s)")
    print(f"Rubric    {len(BENCHMARK_RUBRIC['criteria'])} criteria, "
          f"{BENCHMARK_RUBRIC['total_points']:g} points")
    provider = get_provider()
    model = provider._model_for("grading")  # noqa: SLF001 - script introspection
    print(f"Provider  {provider.name}")
    print(f"Model     {model}")
    print()

    if args.dry_run:
        print("Dry run - no API calls made.")
        return

    totals: list[float] = []
    per_criterion: dict[str, list[float]] = {
        c["id"]: [] for c in BENCHMARK_RUBRIC["criteria"]
    }
    latencies: list[float] = []
    costs: list[float] = []
    all_flags: list[str] = []

    for run in range(1, args.runs + 1):
        started = time.perf_counter()
        try:
            result = grade_submission(
                parsed=parsed,
                rubric=BENCHMARK_RUBRIC,
                assignment_name="Benchmark assignment",
                assignment_description="Fit a model to the data and report a metric.",
                include_images=not args.no_images,
            )
        except GradingError as exc:
            print(f"  run {run}: FAILED - {exc}")
            continue

        elapsed = time.perf_counter() - started
        latencies.append(elapsed)
        totals.append(result["total_score"])
        costs.append(estimate_cost(result["usage"]))
        all_flags.extend(result["flags"])
        for criterion in result["criteria_results"]:
            per_criterion[criterion["criterion_id"]].append(criterion["score"])

        usage = result["usage"]
        cached = usage.get("cache_read_input_tokens", 0)
        print(f"  run {run}: {result['total_score']:6.1f}/100  "
              f"{result['letter_grade']:<2}  {elapsed:5.1f}s  "
              f"in={usage['input_tokens']:>6} out={usage['output_tokens']:>5} "
              f"cached={cached:>6}  ${costs[-1]:.4f}")

    if not totals:
        print("\nEvery run failed. Check ANTHROPIC_API_KEY and your network.")
        sys.exit(1)

    print()
    print("Consistency across runs")
    spread("total score", totals, "/100")
    for cid, scores in per_criterion.items():
        if scores:
            spread(f"  {cid}", scores)

    print()
    print("Performance")
    spread("latency", latencies, "s")
    print(f"  {'cost per submission':22} ${statistics.mean(costs):.4f}  "
          f"(total ${sum(costs):.4f} for {len(costs)} run(s))")
    print(f"  {'projected, 30 students':22} ${statistics.mean(costs) * 30:.2f}")

    if all_flags:
        print()
        print("Flags raised")
        for flag in sorted(set(all_flags)):
            print(f"  {flag:24} {all_flags.count(flag)}/{len(totals)} run(s)")

    print()
    swing = max(totals) - min(totals)
    if swing <= 3:
        verdict = "tight - safe to grade a class with this rubric"
    elif swing <= 8:
        verdict = "acceptable - review borderline grades carefully"
    else:
        verdict = ("wide - tighten the criterion descriptions, or attach an "
                   "instructor reference solution")
    print(f"Verdict: {swing:g}-point spread across {len(totals)} runs - {verdict}")


if __name__ == "__main__":
    main()
