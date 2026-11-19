# Data

All data is synthetic. Study "CT-201" and drug "XR-17" are made up.

`trial_records.csv` is not stored in git. Recreate it from the repo root:

```
python -m clinical_trial_validation.generate_data
```

The seed is fixed, so every run gives the same 5,000 visits (1,000 patients, 6 sites).

## Columns

| Column | Meaning |
|---|---|
| `record_id` | One row = one patient visit (`R00001`) |
| `site_id`, `subject_id` | Trial site (`SITE-01` to `SITE-06`) and patient |
| `arm` | `XR-17` or `Placebo` |
| `age`, `sex` | Patient age (trial enrolls 18-90) and sex |
| `consent_date`, `visit_number`, `visit_date` | No visit may come before consent |
| `systolic_bp` | mmHg |
| `alt_u_l` | ALT liver enzyme, U/L |
| `creatinine_mg_dl` | mg/dL |
| `ae_reported`, `ae_term`, `ae_grade`, `ae_serious` | Adverse event (grade 1 mild to 5 death) |

## Planted problems

So the checks have something to find:

- Missing required fields, visit before consent, impossible age or blood pressure,
  wrong arm code (`XR17`), exact duplicate rows
- A few real ALT outliers in every site
- A safety signal: SITE-04 has many more high ALT values on XR-17

`trial.db` (results, review decisions, audit log) is written to the repo root by the
pipeline and is also not stored in git.
