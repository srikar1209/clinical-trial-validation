"""
Submission: Send all AUTO_CLEAR records to the (fake) outside system, two ways, and compare.

  A. Naive client: send once, as fast as possible
  B. Gateway: rate limit + retries with backoff + circuit breaker + dead-letter queue

Same fake system, same failures (same random seed), so the comparison is fair.
Gateway events are written to the audit log.

Run: python -m clinical_trial_validation.submit
"""
import sqlite3

import pandas as pd

from clinical_trial_validation.audit_log import AuditLog, verify
from clinical_trial_validation.config import DB, REPORTS
from clinical_trial_validation.gateway import Clock, FlakyAPI, Gateway, naive_submit


def run():
    con = sqlite3.connect(DB)
    ids = [r[0] for r in con.execute("SELECT record_id FROM records WHERE decision='AUTO_CLEAR' ORDER BY record_id")]

    naive = naive_submit(FlakyAPI(Clock()), ids)                  # A: send once
    simple = naive_submit(FlakyAPI(Clock()), ids, retries=3)      # B: retry right away
    gw = Gateway(FlakyAPI(Clock()))                               # C: full gateway
    smart = gw.run(ids)

    audit = AuditLog()
    for rid, attempt, status, action in gw.events:
        if action != "SENT" or attempt > 1:            # log retries and final outcomes that needed work
            audit.log(rid, "gateway", action.split(" ")[0], f"attempt {attempt}, HTTP {status}", {"action": action})
    sent_first_try = sum(1 for e in gw.events if e[3] == "SENT" and e[1] == 1)
    audit.log("BATCH", "gateway", "SUBMISSION_DONE",
              f"{len(ids) - len(smart['failed'])}/{len(ids)} sent", {"sent_first_try": sent_first_try})
    audit.flush()

    def row(name, res):
        return {"client": name, "records": len(ids), "failed": len(res["failed"]),
                "failed_pct": round(100 * len(res["failed"]) / len(ids), 1),
                "api_calls": res.get("calls"), "sim_minutes": round(res["seconds"] / 60, 1)}

    rows = [row("A. Send once", naive),
            row("B. Retry 3x right away", simple),
            {**row("C. Gateway, first pass", smart), "failed": len(smart["failed_first_pass"]),
             "failed_pct": round(100 * len(smart["failed_first_pass"]) / len(ids), 1)},
            row("C. Gateway + dead-letter retry", smart)]
    rows[2]["api_calls"] = rows[2]["sim_minutes"] = None
    result = pd.DataFrame(rows)
    result.to_sql("gateway_results", con, if_exists="replace", index=False)
    pd.DataFrame(gw.events, columns=["record_id", "attempt", "http_status", "action"]) \
        .to_sql("gateway_events", con, if_exists="replace", index=False)
    con.close()

    print(result.to_string(index=False))
    n_naive, n_gw = len(naive["failed"]), len(smart["failed"])
    print(f"\nFailed submissions: {n_naive} -> {n_gw}  "
          f"({100 * (n_naive - n_gw) / max(n_naive, 1):.0f}% fewer)")
    ok, n, bad = verify()
    print(f"Audit log: {n} entries, chain {'OK' if ok else 'BROKEN'}")
    out = write_report(result, n_naive, n_gw, (ok, n))
    print(f"Saved {out.relative_to(DB.parent)}")


def write_report(result, n_naive, n_gw, chain):
    """Write reports/submission_report.md with the numbers from this run."""
    ok, n = chain
    fmt = lambda v, spec: "" if v is None or pd.isna(v) else format(v, spec)
    lines = ["# Submission", "",
             "All AUTO_CLEAR records sent to a simulated outside system: 8% random errors, "
             "20 calls/second limit, one 30-second outage. Same seed for every client, so the comparison is fair.", "",
             "| Client | Records | Failed | Failed % | API calls | Simulated minutes |",
             "|---|---|---|---|---|---|"]
    lines += [f"| {r.client} | {r.records:,} | {r.failed:,} | {r.failed_pct}% | {fmt(r.api_calls, ",.0f")} | {fmt(r.sim_minutes, ".1f")} |"
              for r in result.itertuples()]
    lines += ["", f"Failed submissions: {n_naive} -> {n_gw} "
                  f"({100 * (n_naive - n_gw) / max(n_naive, 1):.0f}% fewer).", "",
              "These numbers come from a simulation. They show the idea, not a real system's numbers.", "",
              "## Audit log", "", f"{n:,} entries after submission. Hash chain: {'OK' if ok else 'BROKEN'}.", ""]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "submission_report.md"
    out.write_text("\n".join(lines))
    return out


if __name__ == "__main__":
    run()
