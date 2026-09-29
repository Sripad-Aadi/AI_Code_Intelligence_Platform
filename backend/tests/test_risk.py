"""Steps 10–12 risk tests: rules, synthetic data, features, fitting.

All hermetic — no database, no embeddings, no network. Anything needing the
DB or the jina model is proven by the live train/evaluate/findings run, not
here. What *is* pinned here are the parts that fail silently: the labeling
thresholds, the synthetic generator drifting off its intended classes, the
feature order the artifacts bake in, and the classifier fitting itself.
"""

import numpy as np
from app.risk_model import labeling
from app.risk_model.features import (
    FEATURE_NAMES,
    N_ENGINEERED,
    approx_complexity,
    as_vector,
    clone_dir_for,
    collect_test_paths,
    has_matching_test,
    python_complexity_by_block,
)
from app.risk_model.labeling import (
    LABELS,
    MIN_PER_CLASS,
    generate_synthetic,
    label_from_features,
    synthetic_features,
    top_up_counts,
)
from app.risk_model.train import MODEL_TYPES, fit_classifier


def test_three_classes_in_fixed_order():
    assert LABELS == ("low", "medium", "high")
    assert labeling.LABEL_TO_ID == {"low": 0, "medium": 1, "high": 2}


def test_feature_order_is_frozen():
    """Artifacts and risk_eval assume [embedding | these six], this order."""
    assert FEATURE_NAMES == [
        "complexity",
        "loc",
        "fan_in",
        "fan_out",
        "has_test",
        "churn",
    ]
    assert N_ENGINEERED == 6
    assert as_vector({n: float(i) for i, n in enumerate(FEATURE_NAMES)}) == [
        0.0,
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
    ]


def _feat(**over):
    base = {
        "complexity": 2.0,
        "loc": 12.0,
        "fan_in": 1.0,
        "fan_out": 1.0,
        "has_test": 1.0,
        "churn": 0.0,
    }
    base.update(over)
    return base


def test_label_rules_match_the_documented_thresholds():
    assert label_from_features(_feat()) == "low"
    assert label_from_features(_feat(complexity=10.0)) == "high"
    assert label_from_features(_feat(loc=81.0)) == "high"
    assert label_from_features(_feat(complexity=4.0)) == "medium"
    assert label_from_features(_feat(loc=31.0)) == "medium"
    assert label_from_features(_feat(fan_in=3.0, fan_out=3.0)) == "medium"
    assert label_from_features(_feat(has_test=0.0)) == "medium"
    assert label_from_features(_feat(churn=5.0)) == "medium"
    assert label_from_features(_feat(churn=20.0)) == "high"
    assert label_from_features(_feat(has_test=0.0, complexity=8.0)) == "high"


def test_synthetic_generator_hits_its_intended_classes():
    """Every generated sample, labeled by the real rules, lands intended."""
    samples = generate_synthetic(20, 20, 20)
    assert len(samples) == 60
    for sample in samples:
        feat, actual = synthetic_features(sample)
        assert actual == sample.intended, (
            f"{sample.intended} sample labeled {actual}: {feat}"
        )


def test_synthetic_python_parses_with_real_complexity_spread():
    """Low < medium < high in measured radon complexity (not hand-set)."""
    samples = generate_synthetic(10, 10, 10)
    by_class = {"low": [], "medium": [], "high": []}
    for sample in samples:
        blocks = python_complexity_by_block(sample.code)
        assert blocks, "generated code must parse"
        by_class[sample.intended].append(blocks[0][2])
    assert max(by_class["low"]) < min(by_class["medium"])
    assert max(by_class["medium"]) < min(by_class["high"])


def test_synthetic_is_deterministic():
    first = [s.code for s in generate_synthetic(5, 5, 5)]
    second = [s.code for s in generate_synthetic(5, 5, 5)]
    assert first == second


def test_top_up_fills_each_class_to_minimum():
    need = top_up_counts({"low": 12, "medium": 3, "high": 0})
    assert need == {
        "low": MIN_PER_CLASS - 12,
        "medium": MIN_PER_CLASS - 3,
        "high": MIN_PER_CLASS,
    }
    assert top_up_counts({"low": 60, "medium": 55, "high": 70}) == {
        "low": 0,
        "medium": 0,
        "high": 0,
    }


def test_test_heuristic_matches_by_stem():
    paths = [
        "src/pages/contact.jsx",
        "src/pages/contact.test.jsx",
        "src/app.py",
        "tests/test_app.py",
        "src/util.py",
    ]
    tests = collect_test_paths(paths)
    assert tests == {"src/pages/contact.test.jsx", "tests/test_app.py"}
    assert has_matching_test("src/pages/contact.jsx", tests)
    assert has_matching_test("src/app.py", tests)
    assert not has_matching_test("src/util.py", tests)


def test_approx_complexity_counts_branches():
    assert approx_complexity("def f():\n    return 1\n") == 1
    assert approx_complexity("if a:\n  pass\nfor x in y:\n  pass\n") == 3


def test_clone_dir_layout_matches_attach():
    from pathlib import Path
    from uuid import UUID

    project = UUID("2b04cb8a-09a7-4495-8a94-8af3b230f166")
    got = clone_dir_for(Path("clones"), project, "Sripad-Aadi", "Portfolio")
    assert got == Path("clones") / str(project) / "Sripad-Aadi__Portfolio"


def test_classifier_fits_both_types_and_separates():
    """The fitting itself on trivially separable engineered-only rows."""
    rng = np.random.RandomState(7)
    X = np.zeros((90, 6))
    y = np.zeros(90, dtype=int)
    for i in range(90):
        cls = i % 3
        y[i] = cls
        X[i] = [
            1 + cls * 5 + rng.rand(),
            10 + cls * 30,
            cls,
            cls,
            1 - (cls > 0),
            cls * 3,
        ]
    for model_type in MODEL_TYPES:
        clf = fit_classifier(X, y, model_type)
        pred = clf.predict(X)
        assert (pred == y).mean() > 0.9, f"{model_type} cannot fit separable data"
    try:
        fit_classifier(X, y, "svm")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown model_type must raise")
