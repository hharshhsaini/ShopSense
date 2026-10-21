# ShopSense

A product-search MCP server for the Polaris MCP Hackathon. It exposes the single required tool,
`search_products`, over MCP Streamable HTTP (protocol `2025-11-25`, plain JSON responses), and helps
shoppers find fashion products in the frozen 105,126-product catalog using natural language, explicit
filters, mixed requests and complementary recommendations.

The competition contract lives in [hackathon-brief.md](hackathon-brief.md) and [schemas/](schemas/);
ShopSense keeps the tool name, both schemas, hard-filter semantics and real catalog IDs unchanged.

## How it works

| Stage | What happens | Code |
| --- | --- | --- |
| Validation | Published JSON Schema plus the brief's extra rules (blank string filters, `min_price > max_price`). | `search.py` |
| Explicit filters | Exact, case-insensitive catalog matching as numpy masks; empty queries return the exact filtered page in the requested order from presorted indexes (about 1 ms). | `search.py` |
| Query understanding | Deterministic parser: garment concepts and synonyms, colours, audience (men/women/kids/baby/teen), budgets ("under 2k", "between 500 and 1500", "₹3,000 or more"), ratings, negations ("not black"), occasions ("lazy Sunday", "office", "beach"), conservative typo correction. | `query_parser.py`, `lexicon.py` |
| Mixed vs complementary | "black jeans and white tees" becomes two choices pooled into one ranked list; "a dress with a matching bag" becomes primary dresses plus bag recommendations (dropped when recommendations are off). | `query_parser.py` |
| Retrieval and ranking | BM25F over catalog fields, including the garment noun at the start of each description (names are often internal codes), fused with precomputed `bge-small-en-v1.5` embeddings, plus type, colour, attribute and occasion bonuses and a small rating prior. | `search.py` |
| Abstention | Off-topic requests, brands or garments the catalog does not carry, and impossible budgets return empty arrays instead of random products. | `query_parser.py` |
| Recommendations | Up to five complementary items for the top primary result, filtered by their own constraints and the shopper's audience, preferring matching or neutral colours, with a reason built from catalog facts. | `search.py` |

Explicit filters always win over conflicting query wording. Query constraints (colour, budget, audience,
garment type) are hard constraints. Results are deterministic, so pagination is stable.

## Run locally

Requires Python 3.12+ and Git LFS (the catalog and embedding index are LFS files).

```sh
git lfs install && git lfs pull
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py            # ready in about 5 s; MCP at http://127.0.0.1:8000/mcp, health at /healthz
```

In another terminal:

```sh
python smoke_test.py http://127.0.0.1:8000/mcp    # official contract check
python -m unittest discover -s tests              # unit and behaviour tests
python eval/run_eval.py holdout.json              # local proxy evaluation (not the Bedrock benchmark)
python eval/perf.py http://127.0.0.1:8000/mcp     # latency workload shaped like the benchmark's
```

`index/` holds the precomputed embeddings. Rebuild them only if the catalog or model changes, using
`python build_index.py` (about 25 minutes on a laptop CPU). The server checks the index against the
catalog SHA-256 and falls back to lexical ranking if they do not match.

## Docker

```sh
docker build -t shopsense .
docker run --rm -p 8000:8000 -e MCP_ALLOWED_HOSTS='localhost:*,127.0.0.1:*,YOUR_PUBLIC_HOST:*,YOUR_PUBLIC_HOST' shopsense
```

The image bakes in the catalog, index and embedding model, so it never downloads anything at startup.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Listener |
| `CATALOG_PATH` | `data/products.json` | Catalog file |
| `MCP_ALLOWED_HOSTS` | `localhost:*,127.0.0.1:*,[::1]:*` | Accepted HTTP Host values; add the public host when deployed |
| `MCP_ALLOWED_ORIGINS` | empty | Accepted browser origins |
| `ACCESS_LOG` | `0` | Set to `1` for per-request access logs |

## Deploy on SpringWinter

Create a **Web server** in your SpringWinter project from this repository's Dockerfile, then set:

| Setting | Value |
| --- | --- |
| Port | `8000` (or whatever the platform puts in `PORT`; the server reads it) |
| Health check path | `/healthz` |
| Instance size | at least 2 GB RAM; the server uses about 0.9 GB |
| `MCP_ALLOWED_HOSTS` | your app's hostname, e.g. `myapp.<id>.apps.springwinter.dev,myapp.<id>.apps.springwinter.dev:*`, or `*` to accept any host |

Submit `https://<your app hostname>/mcp`. Builders that clone without Git LFS are handled:
`scripts/fetch_lfs.py` downloads and verifies the catalog and index during the Docker build.

## Deploy to AWS EC2 directly

[deploy/ec2_deploy.sh](deploy/ec2_deploy.sh) creates one arm64 EC2 instance with Docker, an Elastic IP
and a security group (SSH from your IP, port 8000 from the benchmark runner). It then syncs this folder,
builds the image on the instance and waits for `/healthz`.

```sh
aws login
REGION=ap-south-1 RUNNER_CIDR=<runner-ip>/32 deploy/ec2_deploy.sh up   # prints the /mcp URL to submit
deploy/ec2_deploy.sh push      # redeploy after changes
deploy/ec2_deploy.sh logs      # container logs
deploy/ec2_deploy.sh down      # delete every resource it created
```

Run the smoke test and `eval/perf.py` against the public URL before spending a benchmark attempt, and
record each attempt in [ATTEMPTS.md](ATTEMPTS.md).

## Dataset integrity

`data/products.json` is the frozen catalog. Its SHA-256 is
`05b6aa5e8e8c1c8c997d584f8288e432862454f8820531e13473443e83c8f073`. IDs are strings and keep their
leading zeros, and catalog facts are never edited. Prices, ratings and reviews are synthetic. Synthetic
review text is not used for ranking.

`data/english_words.txt.gz` is derived from the public-domain Webster's 2nd word list. It is used only
to avoid "correcting" real English words (for example "weather" to "leather").

## Repository layout

```
server.py            MCP server (official Python SDK v1, stateless Streamable HTTP)
search.py            catalog indexes, filtering, ranking, recommendations
query_parser.py      query interpretation
lexicon.py           reviewed shopping vocabulary mapped to catalog values
build_index.py       offline embedding build
index/               precomputed embeddings and metadata
eval/                local query sets, proxy evaluator, latency workload
tests/               unit and behaviour tests
deploy/              EC2 deployment script
```
