"""
Step 3: Send all AUTO_CLEAR records to the (fake) outside system, two ways, and compare.

  A. Naive client: send once, as fast as possible
  B. Gateway: rate limit + retries with backoff + circuit breaker + dead-letter queue

Same fake system, same failures (same random seed), so the comparison is fair.
Gateway events are written to the audit log.

Run: python -m trial_validation.pipeline.step3_submit
"""
import sqlite3

import pandas as pd

from ..audit_log import AuditLog, verify
from ..config import DB
from ..gateway import Clock, FlakyAPI, Gateway, naive_submit


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


if __name__ == "__main__":
    run()
