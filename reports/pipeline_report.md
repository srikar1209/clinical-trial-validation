# Pipeline

5,000 synthetic records, rules v1.0, tools via MCP (validate_records, lab_zscores, route_records; 30 calls).

## Routing

| Decision | Records | Share |
|---|---|---|
| AUTO_CLEAR | 4,710 | 94.2% |
| HUMAN_REVIEW | 160 | 3.2% |
| QUERY_SITE | 130 | 2.6% |

## Top data errors (sent back to sites)

| Error | Records |
|---|---|
| Visit date is before consent date | 25 |
| Unknown arm | 20 |
| Duplicate record | 20 |
| Missing visit_date | 16 |
| Impossible age | 15 |
| Missing arm | 12 |

## Site safety signal

Share of valid XR-17 visits with ALT z >= 3, and how far each site is from the others (site z).

| Site | % ALT outliers | Site z |
|---|---|---|
| SITE-01 | 0.9% | -0.22 |
| SITE-02 | 0.3% | -0.46 |
| SITE-03 | 0.0% | -0.55 |
| SITE-04 | 7.3% | 2.03 |
| SITE-05 | 0.6% | -0.33 |
| SITE-06 | 0.3% | -0.46 |

Signal: SITE-04 (7.3% of XR-17 visits, site z=2.03).

## Audit log

14,871 entries after the pipeline. Hash chain: OK.
