"""
Shared settings (the "rule book").  ALL DATA IS SYNTHETIC (made up).

Study: a fictional Phase 2 trial "CT-201" testing drug "XR-17" vs placebo.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # repository root
DATA = ROOT / "data"
RECORDS_CSV = DATA / "trial_records.csv"
DB = ROOT / "trial.db"            # results + audit log live here

RULE_VERSION = "v1.0"             # saved with every decision, so you know which rules made it

# ---------------- validation rules (Agent 1)
REQUIRED_FIELDS = ["record_id", "site_id", "subject_id", "visit_date", "consent_date", "arm"]
ALLOWED_ARMS = ["XR-17", "Placebo"]
# Values outside these are impossible -> data entry error
PLAUSIBLE = {
    "age": (18, 90),             # trial only enrolls adults 18-90
    "systolic_bp": (70, 220),    # mmHg
    "alt_u_l": (3, 2000),        # ALT liver enzyme, U/L
    "creatinine_mg_dl": (0.2, 10),
}

# ---------------- outlier rules (Agent 2)
Z_THRESHOLD = 3.0                 # |z| >= 3 = very unusual (only ~0.3% of normal data)
ZSCORE_COLUMNS = ["alt_u_l", "creatinine_mg_dl", "systolic_bp"]

# ---------------- routing rules (Agent 3)
# Severity of an adverse event (AE) uses the common 1-5 grade scale:
#   1 mild, 2 moderate, 3 severe, 4 life-threatening, 5 death
HIGH_SEVERITY_GRADE = 3
