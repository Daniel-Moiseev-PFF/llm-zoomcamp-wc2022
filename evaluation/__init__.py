"""Offline evaluation: retrieval arms (Hit Rate / MRR) + agent prompt variants.

Distinct from `monitoring/`, which scores live traffic. Everything here runs
against a fixed, committed dataset so two runs are comparable.
"""

from pathlib import Path

DEFAULT_MODEL = "gpt-5.4-mini"
DATA_DIR = Path(__file__).parent / "data"  # committed CSVs — ground truth + results
