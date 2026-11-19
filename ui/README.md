# UI

Streamlit app with 5 pages. It reads `trial.db`, so run the pipeline first. From the repo root:

```bash
python -m clinical_trial_validation.run_all
streamlit run ui/app.py
```

Open the URL Streamlit prints (usually http://localhost:8501). Ctrl+C stops it.

Review decisions made on page 2 are saved to `trial.db` and the audit log. Running
`run_all` again starts fresh and removes them.

See [docs/APP_GUIDE.md](../docs/APP_GUIDE.md) for what each page shows and which table it reads.

## Troubleshooting
- `no such table: records`: run `python -m clinical_trial_validation.run_all` first.
- MCP mode hangs or fails: try `python -m clinical_trial_validation.run_all --local` (same results, no MCP).
