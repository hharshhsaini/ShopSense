"""MCP latency check shaped like the benchmark's performance workload.

python eval/perf.py [URL]   (default http://127.0.0.1:8000/mcp)

50 empty-query filter/field-sort calls (limit=10, offset=0), 20 warm-up calls,
then 3 x (concurrency 1, concurrency 5). Each response is checked against the
exact expected page computed from the catalog file, like the organizer does.
"""
import asyncio
import json
import math
import random
import sys
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]


def expected_page(products, args):
    f = args.get('filters', {})
    rows = [p for p in products
            if all(str(p[k]).casefold() == f[k].casefold() for k in
                   ('category', 'product_type', 'color', 'audience', 'section', 'pattern') if k in f)
            and f.get('min_price', 0) <= p['price']['amount'] <= f.get('max_price', math.inf)
            and ('min_rating' not in f or (p['rating']['average'] or 0) >= f['min_rating'])
            and p['rating']['count'] >= f.get('min_review_count', 0)]
    rows.sort(key=lambda p: p['id'])
    sort_by, desc = args.get('sort_by', 'relevance'), args.get('sort_order', 'desc') == 'desc'
    if sort_by == 'rating':
        rated = sorted([p for p in rows if p['rating']['average'] is not None],
                       key=lambda p: p['rating']['average'], reverse=desc)
        rows = rated + [p for p in rows if p['rating']['average'] is None]
    elif sort_by in ('price', 'review_count', 'id'):
        key = {'price': lambda p: p['price']['amount'], 'review_count': lambda p: p['rating']['count'],
               'id': lambda p: p['id']}[sort_by]
        rows.sort(key=key, reverse=desc)
    return [p['id'] for p in rows[:10]]


def make_pool(products, n=50, seed=11):
    rng = random.Random(seed)
    values = {k: sorted({p[k] for p in products}) for k in ('category', 'product_type', 'color', 'audience', 'pattern')}
    pool = []
    for _ in range(n):
        filters = {}
        for k in rng.sample(list(values), rng.randint(1, 2)):
            filters[k] = rng.choice(values[k][:25])
        if rng.random() < 0.5:
            filters['max_price'] = rng.choice([999, 1999, 2999, 4999])
        if rng.random() < 0.3:
            filters['min_rating'] = rng.choice([3, 4, 4.5])
        pool.append({'filters': filters, 'sort_by': rng.choice(['price', 'rating', 'review_count', 'id', 'relevance']),
                     'sort_order': rng.choice(['asc', 'desc']), 'limit': 10, 'offset': 0})
    return pool


async def call(session, args, expected):
    t = time.perf_counter()
    try:
        result = await asyncio.wait_for(session.call_tool('search_products', args), 10)
        ok = not result.isError and [r['id'] for r in result.structuredContent['results']] == expected
    except Exception:
        ok = False
    ms = (time.perf_counter() - t) * 1000
    return ms if ok else 10000.0, ok


async def workload(session, pool, expected, concurrency):
    sem = asyncio.Semaphore(concurrency)
    async def one(i):
        async with sem:
            return await call(session, pool[i], expected[i])
    return await asyncio.gather(*(one(i) for i in range(len(pool))))


async def main(url):
    products = json.loads((ROOT / 'data/products.json').read_text())
    pool = make_pool(products)
    expected = [expected_page(products, a) for a in pool]
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for i in range(20):
                await call(session, pool[i % len(pool)], expected[i % len(pool)])
            timed = []
            for _ in range(3):
                for c in (1, 5):
                    timed += await workload(session, pool, expected, c)
    ms = sorted(t for t, _ in timed)
    correct = sum(ok for _, ok in timed) / len(timed)
    p95 = ms[math.ceil(0.95 * len(ms)) - 1]
    print(f'calls={len(ms)} correct={correct:.3f} p50={ms[len(ms) // 2]:.1f}ms p95={p95:.1f}ms '
          f'perf_points={5 * correct * max(0, min(1, (2000 - p95) / 1800)):.2f}/5')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000/mcp'))
