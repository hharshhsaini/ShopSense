# Benchmark attempts (5 accepted runs; best complete score counts)

Before spending an attempt: `python -m unittest discover -s tests`, `python eval/run_eval.py`,
`python eval/run_eval.py holdout.json`, `python smoke_test.py http://HOST:8000/mcp` and
`python eval/perf.py http://HOST:8000/mcp` against the deployed URL, all green.

| # | Date | Git commit | Index (model / sha) | Endpoint | Score | Validity | Ranking | Unusual | Mixed | Recs | Perf (p95) | Errors | Changes since previous |
|---|------|-----------|---------------------|----------|-------|----------|---------|---------|-------|------|-----------|--------|------------------------|
| 1 |      | 7712970 + deploy fix | bge-small-en-v1.5 / 05b6aa5e | http://52.20.255.206:8000/mcp (us-east-1, c7g.large) |       |          |         |         |       |      |           |        | first submission        |

Pre-submission checks for attempt 1 (2026-10-21): smoke test PASS on the public URL; perf workload 300/300
correct, p95 68 ms measured inside the instance, p95 463 ms from India (network round trip).
| 2 |      |           |                     |          |       |          |         |         |       |      |           |        |                         |
| 3 |      |           |                     |          |       |          |         |         |       |      |           |        |                         |
| 4 |      |           |                     |          |       |          |         |         |       |      |           |        |                         |
| 5 |      |           |                     |          |       |          |         |         |       |      |           |        |                         |

Rules of thumb: change one thing per attempt, keep the previous best image tagged so it can be
restored, and never resubmit while a run is queued (it reserves an attempt).
