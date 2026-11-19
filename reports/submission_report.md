# Submission

All AUTO_CLEAR records sent to a simulated outside system: 8% random errors, 20 calls/second limit, one 30-second outage. Same seed for every client, so the comparison is fair.

| Client | Records | Failed | Failed % | API calls | Simulated minutes |
|---|---|---|---|---|---|
| A. Send once | 4,710 | 758 | 16.1% | 4,710 | 6.0 |
| B. Retry 3x right away | 4,710 | 99 | 2.1% | 5,422 | 6.9 |
| C. Gateway, first pass | 4,710 | 1 | 0.0% |  |  |
| C. Gateway + dead-letter retry | 4,710 | 0 | 0.0% | 5,220 | 7.6 |

Failed submissions: 758 -> 0 (100% fewer).

These numbers come from a simulation. They show the idea, not a real system's numbers.

## Audit log

15,827 entries after submission. Hash chain: OK.
