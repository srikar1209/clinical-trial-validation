"""
Run every step in order: generate data -> agent pipeline -> submission gateway.

Run from the repo root:
    python -m clinical_trial_validation.run_all            (agents call their tools through MCP)
    python -m clinical_trial_validation.run_all --local    (agents call the same tools directly, no MCP)
Then:  streamlit run ui/app.py
"""
import sys

from clinical_trial_validation import generate_data, pipeline, submit


def main(use_mcp=True):
    print("=== Step 1: generate 5,000 synthetic records ===")
    generate_data.build()
    print(f"\n=== Step 2: agent pipeline, tools via {'MCP' if use_mcp else 'local'} ===")
    pipeline.run(use_mcp=use_mcp)
    print("\n=== Step 3: submit cleared records (naive vs gateway) ===")
    submit.run()
    print("\nDone. Now run:  streamlit run ui/app.py")


if __name__ == "__main__":
    main(use_mcp="--local" not in sys.argv)
