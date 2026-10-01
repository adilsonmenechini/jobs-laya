"""Measure the three screeners on the labeled sample jobs.

    python eval/evaluate.py                      # real Laya checkpoints (GPU/CPU)
    python eval/evaluate.py --backend fake       # FakeEngine, no download
    python eval/evaluate.py --backend heuristic  # heuristics only; no model

Compares three screeners on the same jobs, so each part's contribution shows:
heuristics only, Laya only, and the combined policy. Writes eval/evaluation.md
and the raw rows to eval/results/{backend}.json.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.classifier.engine import (  # noqa: E402
    Engine,
    EngineResult,
    FakeEngine,
    LayaEngine,
    LayaView,
)
from app.classifier.laya_classifier import LayaInspiredClassifier  # noqa: E402
from app.classifier.laya_job_classifier import (  # noqa: E402
    ROLE_FAMILIES_IN_PROFILE,
    SENIORITY_VALUE,
    LayaJobClassifier,
)
from app.classifier.questions import job_state  # noqa: E402

SAMPLES = ROOT / "eval" / "samples"
SCREENERS = ("heuristics_only", "laya_only", "combined")
MATCHES = ("high", "medium", "low")


class _NoEngine:
    """Makes the policy take its documented fallback path (heuristics verdict)."""

    device = "none"
    ready = False

    def predict(self, states: list[dict[str, str]]) -> list[EngineResult]:
        raise RuntimeError("backend sem engine Laya")


class _CachedEngine:
    """Replays the one forward pass already paid for this job."""

    def __init__(self, result: EngineResult) -> None:
        self._result = result
        self.device = "cached"
        self.ready = True

    def predict(self, states: list[dict[str, str]]) -> list[EngineResult]:
        return [self._result for _ in states]


def laya_only(view: LayaView, profile: dict) -> tuple[str, float]:
    """Score from Laya's answers alone: the four components the model reads,
    with the heuristic-only weights renormalized (0.20+0.15+0.30+0.10 = 0.75),
    so dropping cloud/experience/ai does not cap the score below the thresholds.
    """
    weights = LayaInspiredClassifier.WEIGHTS
    components = {
        "title": 100.0 if view.role_family in ROLE_FAMILIES_IN_PROFILE else 0.0,
        "seniority": SENIORITY_VALUE[min(2, max(0, view.seniority))],
        "skills": round(view.skill_fit * 100, 2),
        "remote": 100.0 if (view.remote >= 0.5 or not profile.get("remote_required")) else 0.0,
    }
    available = sum(weights[key] for key in components)
    score = round(sum(components[key] * weights[key] for key in components) / available, 2)
    match = "high" if score >= 80 else "medium" if score >= 60 else "low"
    return match, score


def build_engine(backend: str, device: str | None) -> Engine | None:
    if backend == "heuristic":
        return None
    return FakeEngine() if backend == "fake" else LayaEngine(device=device)


def evaluate(engine: Engine | None, profile: dict, labels: list[dict]) -> list[dict]:
    heuristics = LayaInspiredClassifier(profile)
    rows = []
    for label in labels:
        job = json.loads((SAMPLES / label["file"]).read_text(encoding="utf-8"))
        base = heuristics.classify(job)
        reading = None
        if engine is not None:
            [reading] = engine.predict([job_state(job)])
            model, laya_ms = reading.model, round(reading.latency_ms, 1)
            l_match, l_score = laya_only(reading.view, profile)
            policy_engine: Engine = _CachedEngine(reading)
        else:
            model, laya_ms = None, None
            l_match, l_score = None, None
            policy_engine = _NoEngine()
        combined = LayaJobClassifier(profile, policy_engine).classify(job)
        rows.append(
            {
                "file": label["file"],
                "lang": label["lang"],
                "expected": label["expected"],
                "note": label["note"],
                "heuristics_only": {"match": base["match"], "score": base["score"]},
                "laya_only": None if l_match is None else {"match": l_match, "score": l_score},
                "combined": {"match": combined["match"], "score": combined["score"]},
                "model": model,
                "laya_ms": laya_ms,
                "laya_answers": None
                if reading is None
                else {
                    "role_family": reading.view.role_family,
                    "remote": round(reading.view.remote, 3),
                    "skill_fit": round(reading.view.skill_fit, 3),
                    "seniority": reading.view.seniority,
                },
            }
        )
    return rows


def report(rows: list[dict], backend: str, device: str | None) -> str:
    total = len(rows)
    by_class = {m: [r for r in rows if r["expected"] == m] for m in MATCHES}
    by_lang = {lang: [r for r in rows if r["lang"] == lang] for lang in ("en", "pt")}

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

    latencies: dict[str, list[float]] = {}
    for row in rows:
        if row["model"] is not None:
            latencies.setdefault(row["model"], []).append(row["laya_ms"])
    if backend == "heuristic":
        engine_line = "heuristics only (no model)"
    else:
        median = ", ".join(
            f"{m} {statistics.median(v):.0f} ms" for m, v in sorted(latencies.items())
        )
        engine_line = f"backend `{backend}` ({device or 'auto'}, median: {median})"

    lines = [
        "# Evaluation",
        "",
        f"Measured with `python eval/evaluate.py --backend {backend}` — {engine_line} — over the "
        f"{total} labeled jobs in `eval/samples/` ({len(by_class['high'])} high, "
        f"{len(by_class['medium'])} medium, {len(by_class['low'])} low; "
        f"{len(by_lang['en'])} English, {len(by_lang['pt'])} Portuguese).",
        "This is a small, hand-made inbox: the numbers show how the parts work together, not how "
        "the classifier does on real postings. Label a few hundred of your own jobs and refit the "
        "thresholds before trusting a verdict.",
        "",
        "| Screener | Exact matches | high | medium | low |",
        "|---|---|---|---|---|",
        screener_row("Heuristics only", "heuristics_only"),
        *(
            [screener_row("Laya only", "laya_only")]
            if rows[0]["laya_only"] is not None
            else ["| Laya only | — (backend without model) | — | — | — |"]
        ),
        screener_row("Combined policy", "combined"),
        "",
        "| Job | Expected | Heuristics only | Laya only | Combined | Laya answers |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        cells = []
        for key in SCREENERS:
            cell = row[key]
            if cell is None:
                cells.append("—")
                continue
            mark = "" if cell["match"] == row["expected"] else " ✗"
            cells.append(f"{cell['match']} ({cell['score']:.0f}){mark}")
        answers = row["laya_answers"]
        answers_cell = (
            "—"
            if answers is None
            else f"{answers['role_family']}, remote {answers['remote']:.2f}, "
            f"fit {answers['skill_fit']:.2f}, sen {answers['seniority']}"
        )
        lines.append(
            f"| {row['file']} | {row['expected']} | {cells[0]} | {cells[1]} | {cells[2]} "
            f"| {answers_cell} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("laya", "fake", "heuristic"), default="laya")
    parser.add_argument("--device", default=None, help="cuda, cpu or mps (default: auto)")
    parser.add_argument("--out", default=str(ROOT / "eval" / "evaluation.md"))
    args = parser.parse_args()

    labels = json.loads((SAMPLES / "labels.json").read_text(encoding="utf-8"))
    profile = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
    engine = build_engine(args.backend, args.device)

    rows = evaluate(engine, profile, labels)
    device = getattr(engine, "device", None)
    markdown = report(rows, args.backend, device)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(markdown + "\n", encoding="utf-8")
    results_dir = ROOT / "eval" / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / f"{args.backend}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
