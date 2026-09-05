"""Every filesystem location in the project, derived from this file's location.

Import this instead of computing paths per script, so scripts can be run from
anywhere: `from paths import DATASET`.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset"
GOLDEN = ROOT / "golden"
ANALYSIS = ROOT / "analysis"
DASHBOARD = ROOT / "dashboard"
DOCS = ROOT / "docs"

JOINS = ANALYSIS / "joins"
ROUTING = ANALYSIS / "routing"
SLACK = ANALYSIS / "slack"
INTEGRITY = ANALYSIS / "integrity"
PROFILE = ANALYSIS / "profile"
CRM = ANALYSIS / "crm"
