"""Score saved result files again with the current scorer (no model needed).

    python eval/rescore.py            prints the table used in the README
    python eval/rescore.py --write    also updates the result files
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_eval", ROOT / "eval" / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)

items = {i["id"]: i for i in json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))}
for path in sorted((ROOT / "eval" / "results").glob("*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["results"]
    by_category: dict[str, list[bool]] = {}
    for row in rows:
        answer = row["answer"].split("\n\n(Warning")[0]
        row["correct"], row["reason"] = run_eval.score(items[row["id"]], answer, row["tool_calls"])
        row["expected"] = items[row["id"]]["expect"]
        by_category.setdefault(row["category"], []).append(row["correct"])
    correct = sum(r["correct"] for r in rows)
    data["summary"].update({
        "questions": len(rows), "correct": correct,
        "accuracy_percent": round(100 * correct / len(rows), 1),
        "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2],
        "by_category": {c: f"{sum(v)}/{len(v)}" for c, v in by_category.items()}})
    print(f"{path.name}: {correct}/{len(rows)}  failed: "
          + ", ".join(f"Q{r['id']}" for r in rows if not r["correct"]))
    if "--write" in sys.argv:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
