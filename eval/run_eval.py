"""Run the evaluation questions through the agent and score the answers.

    python eval/run_eval.py                      all 40 questions, default model
    python eval/run_eval.py --model llama3.2:3b  another Ollama model
    python eval/run_eval.py --ids 1 9 15         only these questions

A data answer is correct when it contains the expected number (counts exactly,
percentages within 0.05) or the expected name, AND the agent called a tool.
A "no data" answer is correct when it says the graph has no data and gives no
invented number. Results are saved after every question in eval/results/.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lho_demo import config as cfg          # noqa: E402
from lho_demo.agent import Agent            # noqa: E402

REFUSAL_MARKERS = [
    "no data", "no records", "no record", "not available", "does not contain", "doesn't contain",
    "no information", "not in the graph", "outside", "do not have", "don't have", "cannot answer",
    "can't answer", "not a known", "is not known", "not included", "no tests", "no results",
    "not part of", "not present", "no such", "unable to", "geen",
]
TIE_MARKERS = ["the same", "equal", "no difference", "identical"]
ALLOWED_IN_REFUSAL = {0.0, 6.0, 2019.0, 2025.0}


def numbers_in(text: str) -> list[float]:
    cleaned = re.sub(r"(?i)parainfluenza[- ]?3|\bPI-?3\b|\bH\dN\d\b", "", text)   # digits inside names
    cleaned = re.sub(r"(?<=\d)[,   ](?=\d{3}\b)", "", cleaned)      # 1,234 -> 1234
    return [float(n) for n in re.findall(r"(?<![\w.-])\d+(?:\.\d+)?", cleaned)]


def has_text(answer: str, wanted: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(wanted.lower()) + r"(?![a-z0-9])", answer.lower()) is not None


def score(item: dict, answer: str, calls: list[dict]) -> tuple[bool, str]:
    """calls: the tool calls the agent made, each {"tool": ..., "arguments": {...}}."""
    expect = item["expect"]
    found = numbers_in(answer)
    used_tool = bool(calls)
    if expect["refusal"]:
        if not any(marker in answer.lower() for marker in REFUSAL_MARKERS):
            return False, "did not say that the graph has no data"
        invented = [n for n in found if n not in ALLOWED_IN_REFUSAL and n not in numbers_in(item["question"])]
        return (not invented, f"gave numbers {invented}" if invented else "ok")
    if not used_tool:
        return False, "answered without calling a tool"
    if expect.get("compare"):
        # A ranking only counts when the groups were really compared: one call grouped by
        # that dimension, or at least two separate calls. A guess that happens to be right fails.
        stats = [c for c in calls if c["tool"] == "test_statistics"]
        grouped = any(str(c["arguments"].get("group_by", "")) == expect["compare"] for c in stats)
        if not grouped and len(stats) < 2:
            return False, f"named a winner without comparing the groups (no group_by={expect['compare']})"
        low = answer.lower()
        if any(marker in low for marker in REFUSAL_MARKERS):
            return False, "said there is no data, although the graph has the answer"
        if any(marker in low for marker in TIE_MARKERS):
            return False, "said the groups are equal"

        def first(names):                       # position of the first mention, or None
            spots = [m.start() for n in names
                     for m in [re.search(r"(?<![a-z0-9])" + re.escape(str(n).lower()) + r"(?![a-z0-9])", low)] if m]
            return min(spots) if spots else None
        winner, rival = first(expect["any_text"]), first(expect.get("rivals", []))
        if winner is None:
            return False, f"expected one of {expect['any_text']}"
        if rival is not None and rival < winner:
            return False, "named another group before the winner (a list of groups is not an answer)"
    for number in expect["numbers"]:
        tolerance = 0.05 if float(number) != int(number) else 0
        if not any(abs(n - number) <= tolerance + 1e-9 for n in found):
            return False, f"expected {number}, answer has {found}"
    if expect["any_text"] and not any(has_text(answer, t) for t in expect["any_text"]):
        return False, f"expected one of {expect['any_text']}"
    for text in expect["all_text"]:
        if not has_text(answer, text):
            return False, f"expected '{text}'"
    return True, "ok"


def keep_awake() -> None:
    """On Windows, stop the computer from going to sleep while this process runs.

    A long run with nobody at the keyboard otherwise pauses when the laptop sleeps.
    The request ends by itself when the process exits; no power setting is changed.
    """
    if sys.platform == "win32":
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=cfg.PROVIDER)
    parser.add_argument("--model", default=cfg.MODEL)
    parser.add_argument("--ids", nargs="*", type=int)
    parser.add_argument("--tag", default="", help="suffix for the result file name")
    parser.add_argument("--resume", action="store_true",
                        help="continue a stopped run: skip questions already in the result file")
    parser.add_argument("--max-seconds", type=float, default=600,
                        help="with --resume, redo answers slower than this (the machine was stalled)")
    args = parser.parse_args()

    items = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    if args.ids:
        items = [i for i in items if i["id"] in args.ids]
    name = re.sub(r"[^\w.-]+", "_", f"{args.provider}_{args.model}{args.tag}")
    out = ROOT / "eval" / "results" / f"{name}.json"
    rows: list[dict] = []
    if args.resume and out.exists():
        rows = [r for r in json.loads(out.read_text(encoding="utf-8"))["results"]
                if r["seconds"] <= args.max_seconds]
        done = {r["id"] for r in rows}
        items = [i for i in items if i["id"] not in done]
        print(f"Resuming: {len(rows)} answers kept, {len(items)} questions to go.", flush=True)
    started = time.time()
    keep_awake()
    async with Agent(args.provider, args.model) as agent:
        for item in items:
            try:
                result = await agent.ask(item["question"])
            except Exception as error:                       # keep going; record the failure
                result = {"answer": f"ERROR: {error}", "steps": [], "seconds": 0.0}
            calls = [{"tool": s["tool"], "arguments": s["arguments"]} for s in result["steps"]]
            correct, reason = score(item, result["answer"], calls)
            rows.append({"id": item["id"], "category": item["category"], "question": item["question"],
                         "expected": item["expect"], "answer": result["answer"], "correct": correct,
                         "reason": reason, "seconds": result["seconds"], "tool_calls": calls})
            print(f"{'PASS' if correct else 'FAIL'} {item['id']:>2} [{result['seconds']:>5.0f} s] "
                  f"{item['question'][:60]} | {reason if not correct else result['answer'][:70]}",
                  flush=True)
            rows.sort(key=lambda r: r["id"])
            by_category: dict[str, list[bool]] = {}
            for row in rows:
                by_category.setdefault(row["category"], []).append(row["correct"])
            summary = {
                "model": agent.model_name, "questions": len(rows),
                "correct": sum(r["correct"] for r in rows),
                "accuracy_percent": round(100 * sum(r["correct"] for r in rows) / len(rows), 1),
                "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2],
                "mean_seconds": round(sum(r["seconds"] for r in rows) / len(rows), 1),
                "by_category": {c: f"{sum(v)}/{len(v)}" for c, v in by_category.items()},
                "total_minutes": round((time.time() - started) / 60, 1),
            }
            out.write_text(json.dumps({"summary": summary, "results": rows}, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
