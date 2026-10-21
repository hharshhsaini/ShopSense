"""Self-test a deployed endpoint the way the organizer's runner does: over MCP, scored by category.

python eval/remote_benchmark.py [URL]   (default http://127.0.0.1:8000/mcp)

Checks discovery (protocol, tool list, exact schemas), validity (invalid calls must error; exact
empty-query filter pages; field sorting; repeat and larger-prefix pagination probes; schema, unique
and known IDs, recommendation references), then semantic categories from eval/queries.json and
eval/holdout.json graded with catalog facts (a proxy for Bedrock), then the latency workload.
The total uses the brief's weights; treat it as an estimate, not the official score.
"""
import asyncio
import json
import math
import sys
import time
from pathlib import Path

from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from perf import expected_page, make_pool, workload  # noqa: E402
from run_eval import grade, ndcg  # noqa: E402

ROOT = HERE.parent
INPUT_SCHEMA = json.loads((ROOT / 'schemas/input.schema.json').read_text())
OUTPUT_SCHEMA = json.loads((ROOT / 'schemas/output.schema.json').read_text())
OUTPUT = Draft202012Validator(OUTPUT_SCHEMA)

INVALID = [{'limit': 0}, {'limit': 101}, {'offset': -1}, {'sort_by': 'popularity'}, {'extra': 1},
           {'filters': {'color': '  '}}, {'filters': {'min_price': 5, 'max_price': 1}}, {'query': None},
           {'filters': {'min_rating': 6}}, {'include_recommendations': 'yes'}]


async def call(session, args):
    """(structured result or None for an MCP error, milliseconds)."""
    t = time.perf_counter()
    try:
        res = await asyncio.wait_for(session.call_tool('search_products', args), 10)
        out = None if res.isError else res.structuredContent
    except Exception:
        out = None
    return out, (time.perf_counter() - t) * 1000


def structural_ok(out, known, args):
    try:
        OUTPUT.validate(out)
    except Exception:
        return False
    ids = [r['id'] for r in out['results']]
    recs = out['recommendations']
    page = set(ids)
    return (len(ids) == len(set(ids)) and all(i in known for i in ids)
            and len(ids) <= args.get('limit', 10)
            and (recs == [] if not args.get('include_recommendations') or not ids else True)
            and all(r['id'] in known and r['for_product_id'] in page and r['id'] not in page for r in recs)
            and len({r['id'] for r in recs}) == len(recs))


async def validity(session, products, by_id):
    scores = []
    for args in INVALID:
        out, _ = await call(session, args)
        scores.append(1.0 if out is None else 0.0)
    for args in make_pool(products, n=20, seed=5):
        out, _ = await call(session, args)
        if out is None:
            scores.append(0.0)
            continue
        ids = [r['id'] for r in out['results']]
        checks = [structural_ok(out, by_id, args), True, ids == expected_page(products, args)]
        again, _ = await call(session, args)
        bigger, _ = await call(session, {**args, 'limit': 20})
        checks.append(again == out and bigger is not None and [r['id'] for r in bigger['results']][:10] == ids)
        scores.append(sum(checks) / 4)
    for q, key in (('black dress', 'price'), ('linen shirt for men', 'rating'), ('sneakers', 'review_count')):
        for order in ('asc', 'desc'):
            args = {'query': q, 'sort_by': key, 'sort_order': order, 'limit': 20}
            out, _ = await call(session, args)
            if out is None:
                scores.append(0.0)
                continue
            rows = [by_id[r['id']] for r in out['results']]
            vals = {'price': lambda p: p['price']['amount'], 'review_count': lambda p: p['rating']['count'],
                    'rating': lambda p: p['rating']['average']}[key]
            present = [vals(p) for p in rows if vals(p) is not None]
            nulls_last = all(vals(p) is None for p in rows[len(present):])
            ordered = present == sorted(present, reverse=order == 'desc') and nulls_last
            scores.append((structural_ok(out, by_id, args) + ordered + 2) / 4)
    return sum(scores) / len(scores), len(scores)


async def semantic(session, by_id):
    cases = json.loads((HERE / 'queries.json').read_text()) + json.loads((HERE / 'holdout.json').read_text())
    cats, lows = {}, []
    for case in cases:
        args = {'query': case['query'], 'limit': 10, 'include_recommendations': case['cat'] == 'rec'}
        out, _ = await call(session, args)
        if out is None or not structural_ok(out, by_id, args):
            cats.setdefault(case['cat'], []).append(0.0)
            continue
        prods = [by_id[r['id']] for r in out['results']]
        cat = case['cat']
        if cat == 'irrelevant':
            s = 1.0 if not prods else 0.0
        elif cat == 'mixed':
            g = [[grade(p, {**c, **{k: v for k, v in case.items() if k == 'max_price'}}) for p in prods]
                 for c in case['choices']]
            best = [max(x) for x in zip(*g)] if prods else []
            s = 0.5 * sum(any(v >= 2 for v in x) for x in g) / len(g) + 0.5 * ndcg(best)
        else:
            s = ndcg([grade(p, case) for p in prods])
            if cat == 'rec':
                spec = {'types': case['rec_types'], **({'max_price': case['rec_max_price']} if 'rec_max_price' in case else {})}
                s = 0.5 * s + 0.5 * ndcg([grade(by_id[r['id']], spec) for r in out['recommendations']], 5)
        cats.setdefault(cat, []).append(s)
        if s < 0.8:
            lows.append((round(s, 2), cat, case['query']))
    return {k: sum(v) / len(v) for k, v in cats.items()}, {k: len(v) for k, v in cats.items()}, lows


async def main(url):
    products = json.loads((ROOT / 'data/products.json').read_text())
    by_id = {p['id']: p for p in products}
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = (await session.list_tools()).tools
            discovery = (init.protocolVersion == '2025-11-25' and [t.name for t in tools] == ['search_products']
                         and tools[0].inputSchema == INPUT_SCHEMA and tools[0].outputSchema == OUTPUT_SCHEMA)
            print(f"discovery: {'PASS' if discovery else 'FAIL'} (protocol {init.protocolVersion}, server {init.serverInfo.name})")
            v, nv = await validity(session, products, by_id)
            cats, counts, lows = await semantic(session, by_id)
            pool = make_pool(products)
            expected = [expected_page(products, a) for a in pool]
            for i in range(20):
                await call(session, pool[i % len(pool)])
            timed = []
            for _ in range(3):
                for c in (1, 5):
                    timed += await workload(session, pool, expected, c)
    ms = sorted(t for t, _ in timed)
    correct = sum(ok for _, ok in timed) / len(timed)
    p95 = ms[math.ceil(0.95 * len(ms)) - 1]
    parts = {
        'Validity and constraints': 25 * v,
        'Ranking relevance': 30 * cats.get('ranking', 0),
        'Unusual or irrelevant': 7.5 * cats.get('unusual', 0) + 7.5 * cats.get('irrelevant', 0),
        'Mixed choices': 15 * cats.get('mixed', 0),
        'Recommendations': 10 * cats.get('rec', 0),
    }
    functional = sum(parts.values())
    eligible = functional >= 85.5 and correct >= 0.95
    parts['Performance'] = 5 * correct * max(0, min(1, (2000 - p95) / 1800)) if eligible else 0.0
    print(f'validity cases: {nv}, semantic cases: {counts}')
    for name, pts in parts.items():
        print(f'  {name:<26} {pts:6.2f}')
    print(f"  {'TOTAL (proxy estimate)':<26} {sum(parts.values()):6.2f} / 100")
    print(f'latency: p50 {ms[len(ms) // 2]:.0f} ms, p95 {p95:.0f} ms, correct {correct:.3f}'
          f"{'' if eligible else ' (performance points need >= 85.5 functional and >= 95% correct)'}")
    for s, cat, q in lows:
        print(f'  low {s:4.2f} [{cat}] {q}')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000/mcp'))
