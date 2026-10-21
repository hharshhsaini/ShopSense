# Benchmark attempts (5 accepted runs; best complete score counts)

Before spending an attempt: `python -m unittest discover -s tests`, `python eval/run_eval.py`,
`python eval/run_eval.py holdout.json`, `python smoke_test.py http://HOST:8000/mcp` and
`python eval/perf.py http://HOST:8000/mcp` against the deployed URL, all green.

| # | Date | Git commit | Index (model / sha) | Endpoint | Score | Validity | Ranking | Unusual | Mixed | Recs | Perf (p95) | Errors | Changes since previous |
|---|------|-----------|---------------------|----------|-------|----------|---------|---------|-------|------|-----------|--------|------------------------|
| 1 |      |           | bge-small-en-v1.5 / |          |       |          |         |         |       |      |           |        | first submission        |
| 2 |      |           |                     |          |       |          |         |         |       |      |           |        |                         |
| 3 |      |           |                     |          |       |          |         |         |       |      |           |        |                         |
| 4 |      |           |                     |          |       |          |         |         |       |      |           |        |                         |
| 5 |      |           |                     |          |       |          |         |         |       |      |           |        |                         |

Rules of thumb: change one thing per attempt, keep the previous best image tagged so it can be
restored, and never resubmit while a run is queued (it reserves an attempt).
