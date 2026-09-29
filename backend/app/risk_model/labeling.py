"""Risk labels (Step 10): the 3-class problem and its v1 weak supervision.

The classes are low/medium/high — *not* a universal bug detector, per the
plan. v1 labels come from deterministic rules over the Step 10 features,
because the two textbook sources do not apply here:

* CodeSearchNet (2M code/NL pairs) has **no risk labels** — it fits
  retrieval, not this classifier, so it was deliberately not used.
* Public defect datasets (Devign/Big-Vul style) are binary, C/C++-heavy,
  and would need a forced mapping onto low/medium/high.

So v1 is honest about what it is: a **heuristic distiller**. The rules below
encode "complex, long, highly-coupled, untested, churning code is riskier",
and the trained model productionizes those rules as a fast classifier that
additionally generalizes through the embedding half of its input. The plan's
100–300 *manually reviewed* examples remain the upgrade path — every sample
records its ``label_source``, and ``manual`` already sorts above the rest.

When real indexed code cannot fill a class (twelve functions cannot span
three risk bands), a seeded synthetic generator tops each class up to a
minimum. Synthetic samples run through the *same* feature code (radon really
parses the generated Python) and the *same* rules, so they are members of
the dataset, not hand-set rows.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from app.risk_model.features import python_complexity_by_block

log = logging.getLogger(__name__)

LABELS = ("low", "medium", "high")
LABEL_TO_ID = {label: i for i, label in enumerate(LABELS)}
LABEL_VERSION = "v1"

# Minimum samples per class after the synthetic top-up (plan: 100+ total).
MIN_PER_CLASS = 50
MAX_SYNTHETIC = 400
SYNTHETIC_SEED = 20260929


def label_from_features(feat: Dict[str, float]) -> str:
    """Deterministic v1 rules: complexity/length/coupling/tests/churn."""
    complexity = feat.get("complexity", 1.0)
    loc = feat.get("loc", 1.0)
    fan_in = feat.get("fan_in", 0.0)
    fan_out = feat.get("fan_out", 0.0)
    has_test = feat.get("has_test", 0.0)
    churn = feat.get("churn", 0.0)

    if (
        complexity >= 10
        or loc > 80
        or (fan_out >= 8 and complexity >= 6)
        or (not has_test and complexity >= 8)
        or churn >= 20
    ):
        return "high"
    if (
        complexity >= 4
        or loc > 30
        or fan_in + fan_out >= 5
        or not has_test
        or churn >= 5
    ):
        return "medium"
    return "low"


@dataclass
class SyntheticSample:
    """One generated training sample (source + non-source features)."""

    code: str
    language: str = "Python"
    fan_in: int = 0
    fan_out: int = 0
    has_test: bool = False
    churn: int = 0
    intended: str = "low"
    label_source: str = "synthetic-v1"
    meta: Dict = field(default_factory=dict)


def _render_low(rng: random.Random, i: int) -> str:
    """Trivial function: complexity 1-2, a few lines."""
    if rng.random() < 0.5:
        return f"def get_value_{i}(record):\n    return record[{rng.randint(0, 3)}]\n"
    return (
        f"def describe_{i}(name):\n"
        f"    label = 'item-' + str(name)\n"
        "    if label:\n"
        "        return label\n"
        "    return 'empty'\n"
    )


def _render_medium(rng: random.Random, i: int, n_branches: int | None = None) -> str:
    """Working function: 4-6 branches, a couple dozen lines."""
    n_branches = n_branches if n_branches is not None else rng.randint(3, 5)
    lines = [f"def process_{i}(items, mode):", "    total = 0", "    kept = []"]
    for b in range(n_branches):
        lines.append(f"    if mode == 'opt{b}':")
        lines.append(f"        total += {b + 1}")
        lines.append("        kept.append(mode)")
    lines.append("    for item in items:")
    lines.append("        if item is None:")
    lines.append("            continue")
    lines.append("        total += 1")
    lines.append("    return total, kept")
    return "\n".join(lines) + "\n"


def _render_high(rng: random.Random, i: int) -> str:
    """Monster function: 10+ branches, nesting, 60+ lines, no tests."""
    n_outer = rng.randint(4, 6)
    lines = [f"def handle_{i}(request, rules, cache):", "    result = {}"]
    for o in range(n_outer):
        lines.append(f"    if request.get('k{o}'):")
        lines.append("        for rule in rules:")
        lines.append("            if rule.enabled:")
        lines.append(f"                if rule.level > {o}:")
        lines.append("                    result[rule.name] = rule.apply(request)")
        lines.append(f"                elif rule.level == {o}:")
        lines.append("                    cache[rule.name] = request")
        lines.append("            while rule.retries:")
        lines.append("                rule.retries -= 1")
        lines.append("                if rule.retries < 0:")
        lines.append("                    break")
    lines.append("    for key in list(result):")
    lines.append("        if key not in cache:")
    lines.append("            del result[key]")
    lines.append("    return result")
    # Pad length without adding decisions.
    for p in range(rng.randint(10, 25)):
        lines.append(f"    tmp_{p} = {p}")
    return "\n".join(lines) + "\n"


def generate_synthetic(
    n_low: int, n_medium: int, n_high: int, seed: int = SYNTHETIC_SEED
) -> List[SyntheticSample]:
    """Seeded Python generator: real radon complexity, assigned context."""
    rng = random.Random(seed)
    samples: List[SyntheticSample] = []
    for i in range(n_low):
        # Always tested: the v1 rules rate any untested function medium or
        # worse, so an untested "low" sample would contradict its class.
        samples.append(
            SyntheticSample(
                code=_render_low(rng, i),
                fan_in=rng.randint(0, 2),
                fan_out=rng.randint(0, 2),
                has_test=True,
                churn=rng.randint(0, 2),
                intended="low",
            )
        )
    for i in range(n_medium):
        tested = rng.random() < 0.3
        samples.append(
            SyntheticSample(
                # Untested mediums stay small: the v1 rules rate untested
                # code with complexity >= 8 as high, which would break the
                # generator's contract with its intended class.
                code=_render_medium(rng, i, n_branches=3 if not tested else None),
                fan_in=rng.randint(0, 3),
                fan_out=rng.randint(1, 4),
                has_test=tested,
                churn=rng.randint(0, 6),
                intended="medium",
            )
        )
    for i in range(n_high):
        samples.append(
            SyntheticSample(
                code=_render_high(rng, i),
                fan_in=rng.randint(0, 4),
                fan_out=rng.randint(3, 9),
                has_test=False,
                churn=rng.randint(2, 12),
                intended="high",
            )
        )
    return samples


def synthetic_features(sample: SyntheticSample) -> Tuple[Dict[str, float], str]:
    """Feature dict + v1 label for a synthetic sample (same code path)."""
    blocks = python_complexity_by_block(sample.code)
    complexity = float(blocks[0][2]) if blocks else 1.0
    loc = float(len(sample.code.splitlines()))
    feat = {
        "complexity": complexity,
        "loc": loc,
        "fan_in": float(sample.fan_in),
        "fan_out": float(sample.fan_out),
        "has_test": 1.0 if sample.has_test else 0.0,
        "churn": float(sample.churn),
    }
    return feat, label_from_features(feat)


def top_up_counts(real_counts: Dict[str, int]) -> Dict[str, int]:
    """How many synthetic samples each class needs to reach MIN_PER_CLASS."""
    need = {}
    for label in LABELS:
        deficit = max(0, MIN_PER_CLASS - real_counts.get(label, 0))
        need[label] = deficit
    total = sum(need.values())
    if total > MAX_SYNTHETIC:
        scale = MAX_SYNTHETIC / total
        need = {label: int(count * scale) for label, count in need.items()}
    return need
