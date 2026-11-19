"""
Clinical trial data validation app.

Run from the repo root:   streamlit run ui/app.py
Needs trial.db first:     python -m clinical_trial_validation.run_all
ALL DATA IS SYNTHETIC.
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # repo root, so the package imports

from clinical_trial_validation.audit_log import AuditLog, verify
from clinical_trial_validation.config import DB, Z_THRESHOLD

st.set_page_config(page_title="Trial Data Validation", layout="wide")


def q(sql, params=()):
    con = sqlite3.connect(DB)
    df = pd.read_sql_query(sql, con, params=params)
    con.close()
    return df


st.sidebar.title("Trial Data Validation")
st.sidebar.caption("Study CT-201 · synthetic data")
page = st.sidebar.radio("Page", ["1. Overview", "2. Human review queue", "3. Record audit trail",
                                 "4. Site safety signals", "5. Submission gateway"])

# =====================================================================================
if page == "1. Overview":
    st.title("Validation pipeline")
    st.graphviz_chart("""digraph { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef3fb", fontname="Helvetica"];
      d [label="5,000 records"]; a1 [label="Agent 1\\nValidate"]; a2 [label="Agent 2\\nZ-score outliers"];
      a3 [label="Agent 3\\nRoute"]; a4 [label="Agent 4\\nReport"];
      ac [label="AUTO_CLEAR", fillcolor="#e6f4ea"]; hr [label="HUMAN_REVIEW", fillcolor="#fff3cd"];
      qs [label="QUERY_SITE", fillcolor="#fdecea"]; log [label="Audit log\\n(hash chain)", shape=cylinder, fillcolor="#f2f2f2"];
      mcp [label="MCP server\\nvalidate_records · lab_zscores · route_records", shape=component, fillcolor="#f3e8fd"];
      d->a1->a2->a3->a4; a3->ac; a3->hr; a3->qs; a1->log [style=dashed]; a2->log [style=dashed]; a3->log [style=dashed];
      a1->mcp [dir=both, style=dotted, color="#7b3fbf"]; a2->mcp [dir=both, style=dotted, color="#7b3fbf"];
      a3->mcp [dir=both, style=dotted, color="#7b3fbf"]; }""")
    via = q("SELECT json_extract(details,'$.via') v FROM audit_log WHERE agent='route' LIMIT 1").v[0]
    st.caption(f"Agents 1 to 3 call their check tools via **{str(via).upper()}**. The tools are fixed rules, not an LLM.")
    rec = q("SELECT decision, COUNT(*) n FROM records GROUP BY decision")
    total = int(rec.n.sum())
    get = lambda d: int(rec.loc[rec.decision == d, "n"].sum())
    c = st.columns(4)
    c[0].metric("Records", f"{total:,}")
    c[1].metric("Auto-cleared", f"{get('AUTO_CLEAR'):,}", f"{100 * get('AUTO_CLEAR') / total:.1f}%")
    c[2].metric("Human review", get("HUMAN_REVIEW"))
    c[3].metric("Sent back to site", get("QUERY_SITE"))

    left, right = st.columns(2)
    with left:
        st.subheader("Why records went to human review")
        hr = q("SELECT reason FROM records WHERE decision='HUMAN_REVIEW'")
        hr["type"] = hr.reason.str.split(":").str[0].str.replace(r"AE grade \d \(severe\)", "AE grade 3+ (severe)", regex=True)
        counts = hr.type.value_counts().rename_axis("reason").reset_index(name="records")
        st.plotly_chart(px.bar(counts, x="records", y="reason", orientation="h", height=280))
    with right:
        st.subheader("Data errors sent back to sites")
        err = q("SELECT errors FROM records WHERE decision='QUERY_SITE'")
        types = pd.Series(["Impossible " + e.split("=")[0] if "outside" in e else e.split("'")[0].strip()
                           for es in err.errors for e in es.split("; ")])
        counts = types.value_counts().rename_axis("error").reset_index(name="records")
        st.plotly_chart(px.bar(counts, x="records", y="error", orientation="h", height=280))

# =====================================================================================
elif page == "2. Human review queue":
    st.title("Human review queue")
    st.caption("High-risk records wait here. A reviewer's decision is written to the audit log.")
    queue = q("""SELECT r.record_id, r.priority, r.site_id, r.subject_id, r.arm, r.ae_term, r.ae_grade,
                        r.ae_serious, r.alt_u_l, r.z_alt_u_l, r.reason
                 FROM records r LEFT JOIN reviews v ON r.record_id = v.record_id
                 WHERE r.decision='HUMAN_REVIEW' AND v.record_id IS NULL
                 ORDER BY CASE r.priority WHEN 'HIGH' THEN 0 ELSE 1 END, r.ae_serious DESC, r.ae_grade DESC""")
    done = q("SELECT COUNT(*) n FROM reviews").n[0]
    st.progress(done / max(done + len(queue), 1), text=f"{done} reviewed · {len(queue)} waiting")
    st.dataframe(queue, hide_index=True, height=300)
    if len(queue):
        st.subheader("Review a record")
        rid = st.selectbox("Record", queue.record_id)
        st.json(queue[queue.record_id == rid].iloc[0].to_dict())
        c1, c2 = st.columns(2)
        reviewer = c1.text_input("Reviewer", "Dr. A. Reviewer")
        decision = c2.selectbox("Decision", ["CONFIRMED_AE", "NOT_CLINICALLY_SIGNIFICANT", "ESCALATE_TO_SAFETY"])
        comment = st.text_area("Comment (required)")
        if st.button("Save decision", type="primary", disabled=not comment.strip()):
            con = sqlite3.connect(DB)
            con.execute("INSERT INTO reviews VALUES (?,?,?,?,?)",
                        (rid, reviewer, decision, comment, datetime.now(timezone.utc).isoformat(timespec="seconds")))
            con.commit()
            con.close()
            log = AuditLog()
            log.log(rid, "human_review", decision, comment, {"reviewer": reviewer})
            log.flush()
            st.success(f"Saved and logged: {rid} → {decision}")
            st.rerun()

# =====================================================================================
elif page == "3. Record audit trail":
    st.title("Audit trail")
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Verify hash chain"):
            ok, n, bad = verify()
            (st.success if ok else st.error)(
                f"{n:,} entries checked. " + ("Chain OK, nothing changed." if ok else f"Broken at entry {bad}."))
    with col1:
        ex = q("SELECT record_id FROM records WHERE decision='HUMAN_REVIEW' LIMIT 1").record_id[0]
        rid = st.text_input("Record ID", ex)
    trail = q("SELECT seq, ts_utc, agent, decision, reason, details, rule_version, entry_hash "
              "FROM audit_log WHERE record_id=? ORDER BY seq", (rid,))
    trail["entry_hash"] = trail.entry_hash.str[:12] + "…"
    st.dataframe(trail, hide_index=True)
    rec = q("SELECT * FROM records WHERE record_id=?", (rid,))
    if len(rec):
        with st.expander("Original record"):
            st.json(rec.iloc[0].dropna().to_dict())
    st.caption("Each entry stores the hash of the previous entry. Editing any old entry breaks the chain.")

# =====================================================================================
elif page == "4. Site safety signals":
    st.title("Site safety signals")
    s = q("SELECT * FROM site_signals ORDER BY site_id")
    fig = px.bar(s, x="site_id", y="pct_alt_outliers", color="site_z", color_continuous_scale="Reds", height=340,
                 labels={"pct_alt_outliers": f"% of XR-17 visits with ALT z ≥ {Z_THRESHOLD}"})
    st.plotly_chart(fig)
    top = s.sort_values("site_z", ascending=False).iloc[0]
    st.warning(f"{top.site_id}: {top.pct_alt_outliers:.1f}% of XR-17 visits have very high ALT "
               f"(site z = {top.site_z}). Possible liver safety signal. Needs medical review.")
    st.subheader("ALT values by site (XR-17 arm, valid records)")
    alt = q("SELECT site_id, alt_u_l FROM records WHERE arm='XR-17' AND decision != 'QUERY_SITE' ORDER BY site_id")
    st.plotly_chart(px.box(alt, x="site_id", y="alt_u_l", points="outliers", height=360, log_y=True,
                           labels={"alt_u_l": "ALT (U/L, log scale)"}))

# =====================================================================================
elif page == "5. Submission gateway":
    st.title("Sending cleared records to the outside system")
    st.caption("Same fake system, same failures. It has random errors (8%), a rate limit (20/s), and a 30-second outage.")
    g = q("SELECT * FROM gateway_results")
    st.dataframe(g, hide_index=True)
    plot = g.drop(index=2) if len(g) > 3 else g
    fig = px.bar(plot, x="client", y="failed", text="failed", height=340, labels={"failed": "Failed submissions"})
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig)
    ev = q("SELECT http_status, action FROM gateway_events WHERE action != 'SENT'")
    ev["action"] = ev.action.str.split(" ").str[0]
    c1, c2 = st.columns(2)
    c1.metric("Retries by the gateway", int((ev.action == "RETRY").sum()))
    c2.metric("Records needing the dead-letter retry", int((ev.action == "DEAD_LETTER").sum()))
    st.markdown("""
- **A. Send once:** every error = a lost record.
- **B. Retry right away:** fixes short errors, but during the outage it just hammers the system and still loses records.
- **C. Gateway:** rate limiter avoids "too many requests", backoff waits longer each time,
  the circuit breaker pauses during the outage, and the dead-letter queue retries leftovers later.""")

st.sidebar.markdown("---")
st.sidebar.caption("Synthetic demo. Built by Srikar Setty.")
