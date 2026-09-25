"""Summarize JD Optimizer results across many postings.

Usage:
    python evaluation/run_eval.py path/to/reports/*.json

Each file is a "full report" downloaded from the app's Export tab. Every
posting is re-scored with the current scoring and fact-check code, so all
numbers are calculated the same way even if the reports were made with
earlier versions of the app.

Reports contain the original postings, which belong to the companies that
wrote them, so keep them out of the repo (see .gitignore) and publish only
the summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factcheck import check  # noqa: E402
from scoring import score  # noqa: E402


def summarize(paths: list[str]) -> str:
    rows, totals = [], {"m": [0, 0], "f": [0, 0], "o": [0, 0], "r": [0, 0]}
    fact_ok = 0
    for p in paths:
        rep = json.loads(Path(p).read_text())
        b, a = score(rep["original"]), score(rep["rewritten_jd"])
        fc = check(rep["original"], rep["rewritten_jd"], rep.get("changes", []))
        fact_ok += fc.ok
        for k, (x, y) in {"m": (b.masculine_count, a.masculine_count),
                          "f": (b.feminine_count, a.feminine_count),
                          "o": (b.other_count, a.other_count),
                          "r": (b.required_count, a.required_count)}.items():
            totals[k][0] += x
            totals[k][1] += y
        rows.append(
            f"| {Path(p).stem} | {rep.get('prompt_version', 'v1')} | "
            f"{b.masculine_count} → {a.masculine_count} | {b.feminine_count} → {a.feminine_count} | "
            f"{b.other_count} → {a.other_count} | {b.required_count} → {a.required_count} | "
            f"{fc.length_change:+.0%} | {len(rep.get('changes', []))} | "
            f"{'✅' if fc.ok else '⚠️ ' + ', '.join(w.fact for w in fc.warnings)} |"
        )
    n = len(paths)
    out = [
        "| Posting | Prompt | Masculine | Feminine | Other flags | Required | Length | Changes | Fact check |",
        "|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        f"**Totals across {n} postings:** masculine-coded {totals['m'][0]} → {totals['m'][1]}, "
        f"feminine-coded {totals['f'][0]} → {totals['f'][1]}, other flagged phrases "
        f"{totals['o'][0]} → {totals['o'][1]}, required qualifications {totals['r'][0]} → {totals['r'][1]}. "
        f"Fact check passed on {fact_ok} of {n}.",
    ]
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(summarize(sys.argv[1:]))
