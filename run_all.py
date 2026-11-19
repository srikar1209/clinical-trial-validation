"""Run every step in order.
   python run_all.py            (agents call their tools through MCP)
   python run_all.py --local    (agents call the same tools directly, no MCP)
Then:  streamlit run app.py"""
import sys

from trial_validation.pipeline import step1_generate_data, step2_pipeline, step3_submit

use_mcp = "--local" not in sys.argv
print("=== Step 1: generate 5,000 synthetic records ===")
step1_generate_data.build()
print(f"\n=== Step 2: agent pipeline, tools via {'MCP' if use_mcp else 'local'} ===")
step2_pipeline.run(use_mcp=use_mcp)
print("\n=== Step 3: submit cleared records (naive vs gateway) ===")
step3_submit.run()
print("\nDone. Now run:  streamlit run app.py")
