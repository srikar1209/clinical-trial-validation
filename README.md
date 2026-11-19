# Clinical Trial Data Validation (demo)

Checks clinical trial records automatically, sends risky ones to a human,
and keeps a tamper-evident audit log of every decision.

> **All data is synthetic.** Study "CT-201" and drug "XR-17" are made up.

## Run it

```bash
pip3 install -r requirements.txt
python3 run_all.py        # about 10 seconds
streamlit run app.py
```

Optional: open Ollama (`llama3.2`) and Agent 4 writes the summary with the LLM.

## How it works

```
5,000 records ─► Agent 1 Validate ─► Agent 2 Z-score ─► Agent 3 Route ─► Agent 4 Report
                      │                    │                 │
                      └────────────────────┴─────────────────┴──► Audit log (hash chain)
                                                             │
                     AUTO_CLEAR ─► Submission gateway ─► outside system
                     HUMAN_REVIEW ─► review queue (decision also logged)
                     QUERY_SITE ─► back to the site to fix
```

### MCP

Agents 1 to 3 don't contain the check logic. They call **tools** served by an MCP server
(`trial_validation/mcp_server.py`: `validate_records`, `lab_zscores`, `route_records`), in batches of 500,
over stdio. `python run_all.py --local` calls the same functions directly; results are identical.
Every audit entry records which tool was used and `"via": "mcp"` or `"local"`.

## Project layout

```
.
├── app.py                      # Streamlit app (5 pages)
├── run_all.py                  # runs steps 1-3 in order
├── requirements.txt
├── data/                       # generated CSV lands here (git-ignored)
└── trial_validation/           # the Python package
    ├── config.py               # all rules in one place (ranges, z threshold, severity)
    ├── checks.py               # the check logic, one record at a time (no AI)
    ├── mcp_server.py           # offers the checks as MCP tools
    ├── tools.py                # same interface for local or MCP tool calls
    ├── agents.py               # the 4 agents
    ├── llm.py                  # optional Ollama client used by Agent 4
    ├── audit_log.py            # append-only log, SHA-256 hash chain + verify(); optional Kafka
    ├── gateway.py              # rate limiter, retries w/ backoff + jitter, circuit breaker, dead-letter queue
    └── pipeline/
        ├── step1_generate_data.py  # 5,000 synthetic visits, planted errors, safety signal at SITE-04
        ├── step2_pipeline.py       # connects the agents with LangGraph
        └── step3_submit.py         # compares 3 ways of sending records to a flaky outside system
```

`trial.db` (results + audit log) is created at the repo root and is git-ignored.

Run a single step from the repo root:

```bash
python3 -m trial_validation.pipeline.step1_generate_data
python3 -m trial_validation.pipeline.step2_pipeline --mcp   # omit --mcp for local tools
python3 -m trial_validation.pipeline.step3_submit
```

## Results from one run (seed fixed, so you get the same)

| | |
| --- | --- |
| Records | 5,000 (1,000 patients, 6 sites) |
| Auto-cleared | 4,710 (94.2%) |
| Human review | 160 (serious AE, AE grade 3+, or lab z ≥ 3) |
| Sent back to site | 130 (data errors) |
| Safety signal | SITE-04: 7.3% of XR-17 visits with ALT z ≥ 3 (others under 1%) |
| Audit log | ~15,800 entries, hash chain verifies; editing one entry is detected |
| Failed submissions | Send once 758 · Retry right away 99 · Gateway 0 |

The submission numbers come from a **simulated** outside system (8% random errors,
20 calls/second limit, 30-second outage). They show the idea, not a real system's numbers.

## Design choices

- **Rules decide, the LLM only writes.** Safety decisions must be predictable and explainable.
- **Bad data is never dropped.** It goes back to the site with the reason.
- **Z-score stats come from valid records only**, so bad data doesn't distort them.
- **Every decision stores the rule version**, so you know which rules made it.
