"""Evaluate classifier on real job samples (eval/samples_real/).

Usage:
    uv run python eval/evaluate_real.py --backend fake
    uv run python eval/evaluate_real.py --backend heuristic
    uv run python eval/evaluate_real.py --backend laya --device cpu
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.classifier.engine import FakeEngine, LayaEngine  # noqa: E402
from app.classifier.laya_classifier import LayaInspiredClassifier  # noqa: E402
from app.classifier.laya_job_classifier import LayaJobClassifier  # noqa: E402

SAMPLES = ROOT / "eval" / "samples_real"
MATCHES = ("high", "medium", "low")


def build_engine(backend: str, device: str | None):
    if backend == "heuristic":
        return None
    return FakeEngine() if backend == "fake" else LayaEngine(device=device)


def evaluate(engine, profile: dict, labels: list[dict], backend: str = "laya") -> list[dict]:
    heuristics = LayaInspiredClassifier(profile)
    rows = []
    for label in labels:
        job = json.loads((SAMPLES / label["file"]).read_text(encoding="utf-8"))
        base = heuristics.classify(job)
        reading = None
        if engine is not None:
            [reading] = engine.predict(
                [{"title": job.get("title", ""), "description": job.get("description", "")[:800]}]
            )
            policy_engine = _CachedEngine(reading)
        else:
            policy_engine = _NoEngine()
        # `backend` is provenance: it records which engine produced the
        # verdict (decision.laya.backend).
        combined = LayaJobClassifier(profile, policy_engine, backend=backend).classify(job)
        rows.append(
            {
                "file": label["file"],
                "source": job.get("source", ""),
                "expected": label["expected"],
                "note": label.get("note", ""),
                "heuristics_only": {"match": base["match"], "score": base["score"]},
                "combined": {"match": combined["match"], "score": combined["score"]},
            }
        )
    return rows


class _NoEngine:
    device = "none"
    ready = False

    def predict(self, states):
        raise RuntimeError("backend sem engine Laya")


class _CachedEngine:
    def __init__(self, result):
        self._result = result
        self.device = "cached"
        self.ready = True

    def predict(self, states):
        return [self._result for _ in states]


def report(rows: list[dict], backend: str) -> str:
    total = len(rows)
    by_class = {m: [r for r in rows if r["expected"] == m] for m in MATCHES}

    def exact(key: str) -> str:
        return f"{sum(r[key]['match'] == r['expected'] for r in rows)}/{total}"

    def class_exact(key: str, match: str) -> str:
        group = by_class[match]
        if not group:
            return "—"
        return f"{sum(r[key]['match'] == match for r in group)}/{len(group)}"

    def screener_row(label: str, key: str) -> str:
        cells = [class_exact(key, match) for match in MATCHES]
        return f"| {label} | {exact(key)} | {' | '.join(cells)} |"

    lines = [
        "# Evaluation (real samples)",
        "",
        f"Backend: `{backend}` — {total} vagas reais rotuladas",
        f"({len(by_class['high'])} high, {len(by_class['medium'])} medium, "
        f"{len(by_class['low'])} low)",
        "",
        "| Screener | Exact matches | high | medium | low |",
        "|---|---|---|---|---|",
        screener_row("Heuristics only", "heuristics_only"),
        screener_row("Combined policy", "combined"),
        "",
        "| Job | Source | Expected | Heuristics | Combined |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        h = row["heuristics_only"]
        c = row["combined"]
        h_mark = "" if h["match"] == row["expected"] else " ✗"
        c_mark = "" if c["match"] == row["expected"] else " ✗"
        lines.append(
            f"| {row['file'][:30]} | {row['source']} | {row['expected']} "
            f"| {h['match']} ({h['score']:.0f}){h_mark} "
            f"| {c['match']} ({c['score']:.0f}){c_mark} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("laya", "fake", "heuristic"), default="fake")
    parser.add_argument("--device", default=None)
    parser.add_argument("--out", default=str(ROOT / "eval" / "evaluation_real.md"))
    args = parser.parse_args()

    labels = json.loads((SAMPLES / "labels.json").read_text(encoding="utf-8"))
    profile = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
    engine = build_engine(args.backend, args.device)

    rows = evaluate(engine, profile, labels, args.backend)
    markdown = report(rows, args.backend)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(markdown + "\n", encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
