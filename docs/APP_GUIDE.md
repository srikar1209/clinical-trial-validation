# App guide

## Setup
```
python -m pip install -r requirements.txt
python -m clinical_trial_validation.run_all      # writes data/trial_records.csv and trial.db
streamlit run ui/app.py
```
Always run from the repo root (the folder with `data/`).

## Files
- `clinical_trial_validation/config.py`     the rule book: required fields, ranges, z threshold, AE severity, rule version
- `clinical_trial_validation/checks.py`     the checks, one record at a time (no AI)
- `clinical_trial_validation/mcp_server.py` serves the checks as MCP tools over stdio
- `clinical_trial_validation/tools.py`      `LocalTools` / `MCPTools`, same `await tools.call(name, args)`
- `clinical_trial_validation/agents.py`     the 4 agents
- `clinical_trial_validation/pipeline.py`   LangGraph graph: validate -> detect_anomalies -> route -> report
- `clinical_trial_validation/audit_log.py`  append-only log with a SHA-256 hash chain, `verify()`
- `clinical_trial_validation/gateway.py`    rate limiter, retries, circuit breaker, dead-letter queue
- `ui/app.py`                               the Streamlit app (reads `trial.db`)

## The whole pipeline
```python
import asyncio
import pandas as pd
from clinical_trial_validation import agents
from clinical_trial_validation.audit_log import AuditLog, verify
from clinical_trial_validation.config import RECORDS_CSV
from clinical_trial_validation.tools import LocalTools, MCPTools

async def main(use_mcp=True):
    audit = AuditLog()
    tools = await MCPTools().start() if use_mcp else LocalTools()   # MCP starts mcp_server.py
    try:
        df = pd.read_csv(RECORDS_CSV)
        df = await agents.validate(df, audit, tools)          # 1. errors + warnings per record
        df = await agents.detect_anomalies(df, audit, tools)  # 2. lab z-scores, stats from valid records only
        df = await agents.route(df, audit, tools)             # 3. AUTO_CLEAR / HUMAN_REVIEW / QUERY_SITE
    finally:
        await tools.close()
    facts, text, signals = agents.report(df, audit)           # 4. summary (+ Ollama text if running)
    audit.flush()
    print(verify())                                           # (ok, entries, first broken seq)

asyncio.run(main())
```
`pipeline.run()` does the same through LangGraph and also saves the tables below.

## MCP tools
Each takes a batch (500 records per call), so 5,000 records = 10 calls per tool.

| Tool | Input | Output per record |
|---|---|---|
| `validate_records` | `records` | `errors`, `warnings` |
| `lab_zscores` | `records`, `stats` (mean, std per arm) | `z`, `anomalies` |
| `route_records` | `items` (record + errors + anomalies) | `decision`, `priority`, `reason` |

## Tables in trial.db
| Table | Written by | Used on page |
|---|---|---|
| `records` | pipeline | 1, 2, 3, 4 |
| `site_signals` | pipeline | 4 |
| `audit_log` | every agent, the gateway, reviewers | 3 |
| `reviews` | reviewers in the app | 2 |
| `gateway_results`, `gateway_events` | submit | 5 |

## App pages
1. **Overview**: pipeline diagram, routing counts, why records went to review, data errors.
2. **Human review queue**: high-risk records. A reviewer's decision needs a comment and is written to the audit log.
3. **Record audit trail**: every entry for one record, plus a button that verifies the whole hash chain.
4. **Site safety signals**: share of XR-17 visits with ALT z >= 3 per site, and ALT values by site.
5. **Submission gateway**: send once vs retry right away vs gateway, against the same flaky system.

## Optional
- **Ollama**: if `ollama serve` is running with `llama3.2`, Agent 4 writes the summary with the LLM.
  It only writes; the rules make every decision. Change with `OLLAMA_URL`, `LLM_MODEL`.
- **Kafka**: set `KAFKA_BOOTSTRAP` and `pip install kafka-python` to also send audit entries to topic `trial-audit`.
