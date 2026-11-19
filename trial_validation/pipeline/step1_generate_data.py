"""
Step 1: Make 5,000 synthetic clinical trial records.  ALL DATA IS MADE UP.

One record = one patient visit. Some visits have an adverse event (AE).

Planted problems (so our checks have something to find):
  - Missing required fields
  - Visit date BEFORE consent date (not allowed: no data before the patient agreed)
  - Impossible values (age 7, blood pressure 400)
  - Wrong arm name ("XR17" instead of "XR-17")
  - Exact duplicate records
  - Real outliers: very high liver enzyme (ALT) in a few patients
  - One site (SITE-04) with many more high ALT values (a real safety signal)

Run: python -m trial_validation.pipeline.step1_generate_data
"""
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..config import DATA, RECORDS_CSV

random.seed(42)
rng = np.random.default_rng(42)

SITES = [f"SITE-0{i}" for i in range(1, 7)]
AE_TERMS = ["Headache", "Nausea", "Fatigue", "Dizziness", "Rash", "Elevated liver enzymes",
            "Injection site reaction", "Fever"]


def make_subjects(n_subjects=1000):
    subjects = []
    for i in range(1, n_subjects + 1):
        site = random.choice(SITES)
        consent = date(2025, 1, 1) + timedelta(days=random.randint(0, 200))
        subjects.append({
            "subject_id": f"{site[-2:]}-{i:04d}",
            "site_id": site,
            "arm": random.choice(["XR-17", "Placebo"]),
            "age": int(np.clip(rng.normal(52, 12), 18, 85)),
            "sex": random.choice(["F", "M"]),
            "consent_date": consent,
        })
    return subjects


def make_visit(rec_id, s, visit_no):
    visit_date = s["consent_date"] + timedelta(days=14 * visit_no + random.randint(-2, 2))
    alt = rng.lognormal(mean=np.log(28), sigma=0.3)       # normal ALT ~ 28 U/L
    if s["arm"] == "XR-17" and s["site_id"] == "SITE-04" and random.random() < 0.08:
        alt *= rng.uniform(4, 8)                          # safety signal at one site
    elif random.random() < 0.004:
        alt *= rng.uniform(5, 10)                         # rare outliers anywhere
    rec = {
        "record_id": f"R{rec_id:05d}",
        "site_id": s["site_id"],
        "subject_id": s["subject_id"],
        "arm": s["arm"],
        "age": s["age"],
        "sex": s["sex"],
        "consent_date": s["consent_date"].isoformat(),
        "visit_number": visit_no,
        "visit_date": visit_date.isoformat(),
        "systolic_bp": int(rng.normal(128, 12)),
        "alt_u_l": round(alt, 1),
        "creatinine_mg_dl": round(rng.normal(0.95, 0.15), 2),
        "ae_reported": "N", "ae_term": "", "ae_grade": None, "ae_serious": "N",
    }
    # About 15% of visits report an adverse event
    if rec["alt_u_l"] > 120 or random.random() < 0.15:
        rec["ae_reported"] = "Y"
        rec["ae_term"] = "Elevated liver enzymes" if rec["alt_u_l"] > 120 else random.choice(AE_TERMS)
        grade = random.choices([1, 2, 3, 4], weights=[60, 30, 8, 2])[0]
        if rec["alt_u_l"] > 150:
            grade = max(grade, 3)
        rec["ae_grade"] = grade
        rec["ae_serious"] = "Y" if grade >= 4 or random.random() < 0.02 else "N"
    return rec


def plant_errors(df):
    idx = df.sample(frac=1, random_state=1).index.tolist()
    take = lambda n: [idx.pop() for _ in range(n)]
    for i in take(40):
        df.loc[i, random.choice(["visit_date", "consent_date", "arm"])] = None     # missing field
    for i in take(25):                                                              # visit before consent
        df.loc[i, "visit_date"] = (date.fromisoformat(df.loc[i, "consent_date"]) - timedelta(days=5)).isoformat()
    for i in take(15):
        df.loc[i, "age"] = random.choice([7, 150, 0])                               # impossible age
    for i in take(10):
        df.loc[i, "systolic_bp"] = random.choice([400, 12])                         # impossible BP
    for i in take(20):
        df.loc[i, "arm"] = "XR17"                                                   # wrong code
    dupes = df.loc[take(20)].copy()                                                 # exact duplicates
    return pd.concat([df, dupes], ignore_index=True)


def build(n_records=5000):
    DATA.mkdir(exist_ok=True)
    subjects = make_subjects()
    rows, rec_id, visit_no = [], 1, 1
    while len(rows) < n_records - 20:      # each round = every patient has one more visit
        for s in subjects:
            rows.append(make_visit(rec_id, s, visit_no))
            rec_id += 1
            if len(rows) >= n_records - 20:
                break
        visit_no += 1
    df = plant_errors(pd.DataFrame(rows))
    df.to_csv(RECORDS_CSV, index=False)
    print(f"Saved {len(df)} records to {RECORDS_CSV}")
    print(f"  sites: {df.site_id.nunique()}, subjects: {df.subject_id.nunique()}")
    print(f"  visits with an adverse event: {(df.ae_reported == 'Y').sum()}")
    print(f"  serious AEs: {(df.ae_serious == 'Y').sum()}")


if __name__ == "__main__":
    build()
