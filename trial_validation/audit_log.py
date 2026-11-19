"""
Audit log: every decision about every record is written here, and never changed.

Each entry has: which record, which agent, what decision, why, which rule version, when.

Tamper-evidence with a HASH CHAIN:
  each entry stores the hash of the entry before it.
  If someone secretly edits an old entry, its hash changes, and the chain "breaks".
  verify() finds the exact entry where it broke.
  (Same idea a bank ledger or blockchain uses.)

Where entries go:
  - SQLite table audit_log (always)
  - Kafka topic "trial-audit" (only if KAFKA_BOOTSTRAP is set and kafka-python is installed)
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

from .config import DB, RULE_VERSION

GENESIS = "0" * 64   # "previous hash" for the very first entry


class AuditLog:
    def __init__(self, db_path=DB):
        self.con = sqlite3.connect(db_path)
        self.con.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            seq INTEGER PRIMARY KEY, ts_utc TEXT, record_id TEXT, agent TEXT, decision TEXT,
            reason TEXT, details TEXT, rule_version TEXT, prev_hash TEXT, entry_hash TEXT)""")
        last = self.con.execute("SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        self.prev_hash = last[0] if last else GENESIS
        self.buffer = []
        self.kafka = self._kafka()

    def _kafka(self):
        server = os.getenv("KAFKA_BOOTSTRAP")
        if not server:
            return None
        try:
            from kafka import KafkaProducer
            return KafkaProducer(bootstrap_servers=server,
                                 value_serializer=lambda v: json.dumps(v).encode())
        except Exception as e:
            print(f"Kafka not available ({e}); using SQLite only")
            return None

    @staticmethod
    def _hash(entry, prev_hash):
        body = json.dumps(entry, sort_keys=True) + prev_hash
        return hashlib.sha256(body.encode()).hexdigest()

    def log(self, record_id, agent, decision, reason, details=None):
        entry = {"ts_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                 "record_id": record_id, "agent": agent, "decision": decision, "reason": reason,
                 "details": json.dumps(details or {}, default=str), "rule_version": RULE_VERSION}
        h = self._hash(entry, self.prev_hash)
        self.buffer.append((entry, self.prev_hash, h))
        self.prev_hash = h
        if self.kafka:
            self.kafka.send("trial-audit", {**entry, "entry_hash": h})
        if len(self.buffer) >= 2000:
            self.flush()

    def flush(self):
        self.con.executemany(
            "INSERT INTO audit_log (ts_utc, record_id, agent, decision, reason, details, rule_version, "
            "prev_hash, entry_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            [(e["ts_utc"], e["record_id"], e["agent"], e["decision"], e["reason"], e["details"],
              e["rule_version"], p, h) for e, p, h in self.buffer])
        self.con.commit()
        self.buffer = []
        if self.kafka:
            self.kafka.flush()


def verify(db_path=DB):
    """Recompute every hash. Returns (ok, number_checked, first_bad_seq)."""
    con = sqlite3.connect(db_path)
    prev = GENESIS
    n = 0
    for row in con.execute("SELECT seq, ts_utc, record_id, agent, decision, reason, details, rule_version, "
                           "prev_hash, entry_hash FROM audit_log ORDER BY seq"):
        seq, *fields, prev_hash, entry_hash = row
        entry = dict(zip(["ts_utc", "record_id", "agent", "decision", "reason", "details", "rule_version"], fields))
        if prev_hash != prev or AuditLog._hash(entry, prev) != entry_hash:
            return False, n, seq
        prev, n = entry_hash, n + 1
    return True, n, None
