"""Risk-model package (Steps 10–12) — real implementation, not scaffolding.

Step 10 defines the problem (see ``labeling.py``): three classes
low/medium/high over the Step 11 input vector (jina 768-d embedding +
six engineered features from ``features.py``). Step 11 trains the
classifier (``train.py``). Step 12 serves predictions (``predict.py``,
surfaced by the ``findings``/``risk`` API routers).
"""
