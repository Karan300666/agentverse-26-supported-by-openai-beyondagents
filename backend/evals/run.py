"""Run the eval suite from backend/:
    uv run python -m evals.run                          # everything once
    uv run python -m evals.run --category adversarial   # one or more categories
    uv run python -m evals.run --only fee hi_book       # specific scenarios
    uv run python -m evals.run --repeat 3 --parallel 4
"""

import argparse
import asyncio
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import logfire
from openai import AsyncOpenAI

from app.core.config import get_settings
from evals.catalog import SCENARIOS
from evals.harness import run_scenario
from evals.models import Scenario

RESULTS_DIR = Path(__file__).parent / "results"
# Checks that prove no unauthorized action or leak happened.
SAFETY_PREFIXES = ("never confirmed", "no confirmation before", "database:", "no leak")


def _select(only: list[str] | None, categories: list[str] | None) -> list[Scenario]:
    known_ids = {s.id for s in SCENARIOS}
    known_categories = {s.category for s in SCENARIOS}
    if only and (unknown := set(only) - known_ids):
        raise SystemExit(f"Unknown scenario ids: {sorted(unknown)}")
    if categories and (unknown := set(categories) - known_categories):
        raise SystemExit(f"Unknown categories: {sorted(unknown)}. Known: {sorted(known_categories)}")
    return [
        s for s in SCENARIOS
        if (not only or s.id in only) and (not categories or s.category in categories)
    ]


async def _run_one(scenario: Scenario, attempt: int, repeat: int, client: AsyncOpenAI, judge_model: str) -> dict[str, Any]:
    label = scenario.id + (f" (run {attempt})" if repeat > 1 else "")
    try:
        results, transcript = await run_scenario(scenario, client, judge_model)
        error = None
    except Exception as exc:
        results, transcript, error = [], None, repr(exc)

    passed = error is None and all(r.passed for r in results)
    safe = None if error else all(r.passed for r in results if r.name.startswith(SAFETY_PREFIXES))

    lines = [f"{'PASS' if passed else 'FAIL'}  {scenario.category:<12} {label}"]
    if error:
        lines.append(f"        crashed: {error}")
    lines += [f"        x {r.name}: {r.detail}" for r in results if not r.passed]
    print("\n".join(lines), flush=True)

    return {
        "scenario": scenario.id,
        "category": scenario.category,
        "run": attempt,
        "passed": passed,
        "safe": safe,
        "error": error,
        "checks": [asdict(r) for r in results],
        "transcript": transcript.as_text() if transcript else None,
    }


async def main(only: list[str] | None, categories: list[str] | None, repeat: int, parallel: int) -> int:
    settings = get_settings()
    if not settings.eval_judge_model:
        raise SystemExit("Set EVAL_JUDGE_MODEL in the root .env (a chat model your OpenAI account can use).")

    token = settings.logfire_token
    logfire.configure(
        token=token.get_secret_value() if token else None,
        service_name="hospital-voice-evals",
        send_to_logfire="if-token-present",
        console=False,
    )

    scenarios = _select(only, categories)
    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    judge_model = settings.eval_judge_model
    jobs = [(s, a) for s in scenarios for a in range(1, repeat + 1)]
    print(f"Running {len(jobs)} runs ({len(scenarios)} scenarios × {repeat}), {parallel} at a time\n")

    gate = asyncio.Semaphore(max(1, parallel))

    async def guarded(scenario: Scenario, attempt: int) -> dict[str, Any]:
        async with gate:
            return await _run_one(scenario, attempt, repeat, client, judge_model)

    # Scenarios that change global settings (rate limits) must run alone, after the rest.
    shared = [j for j in jobs if j[0].tool_calls_per_minute is None]
    solo = [j for j in jobs if j[0].tool_calls_per_minute is not None]
    runs = list(await asyncio.gather(*(guarded(*j) for j in shared)))
    for scenario, attempt in solo:
        runs.append(await _run_one(scenario, attempt, repeat, client, judge_model))

    by_category: dict[str, list[bool]] = defaultdict(list)
    for run in runs:
        by_category[run["category"]].append(run["passed"])
    total = sum(run["passed"] for run in runs)
    crashed = sum(run["error"] is not None for run in runs)

    print("\nBy category:")
    for category, outcomes in sorted(by_category.items()):
        print(f"  {category:<12} {sum(outcomes)}/{len(outcomes)} ({100 * sum(outcomes) / len(outcomes):.0f}%)")
    print(f"\nOverall: {total}/{len(runs)} runs passed ({100 * total / max(len(runs), 1):.0f}%)")
    if crashed:
        print(f"Crashed (not counted as failures of the agent): {crashed}")

    adversarial = [r for r in runs if r["category"] == "adversarial" and r["error"] is None]
    if adversarial:
        unsafe = sum(r["safe"] is False for r in adversarial)
        print(
            f"Adversarial: {unsafe} of {len(adversarial)} attack runs caused an unauthorized action or leak; "
            f"{sum(r['passed'] for r in adversarial)} passed every check."
        )

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(runs, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Saved: {path}")
    return 0 if total == len(runs) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the voice agent eval suite.")
    parser.add_argument("--only", nargs="+", help="scenario ids to run")
    parser.add_argument("--category", nargs="+", dest="categories", help="categories to run")
    parser.add_argument("--repeat", type=int, default=1, help="runs per scenario")
    parser.add_argument("--parallel", type=int, default=4, help="scenarios run at the same time")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.only, args.categories, args.repeat, args.parallel)))