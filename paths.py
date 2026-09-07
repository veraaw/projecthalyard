"""Every filesystem location in the project, derived from this file's location.

Import this instead of computing paths per script, so scripts can be run from
anywhere: `from paths import CURRENT`.

DATASET is the raw September export, read-only and never written. INTAKE holds
the uploads accepted since (golden/intake.py). CURRENT is what every reader
reads: dataset/ with those uploads applied, rewritten by every build.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset"
INTAKE = ROOT / "intake"
GOLDEN = ROOT / "golden"
CURRENT = GOLDEN / "current"
ANALYSIS = ROOT / "analysis"
DASHBOARD = ROOT / "dashboard"
DOCS = ROOT / "docs"
CONFIG = ROOT / "config"

JOINS = ANALYSIS / "joins"
ROUTING = ANALYSIS / "routing"
SLACK = ANALYSIS / "slack"
INTEGRITY = ANALYSIS / "integrity"
PROFILE = ANALYSIS / "profile"
CRM = ANALYSIS / "crm"
