"""Local proxy evaluation: python eval/run_eval.py [queries.json|holdout.json] [--show] [--no-semantic].

Grades with catalog facts only (type, colour, price, audience, text evidence),
mirroring the benchmark's categories. This is a proxy for, not a copy of, the
organizer's Bedrock judgments.
"""
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from search import Catalog  # noqa: E402

HERE = Path(__file__).resolve().parent


def ok_constraints(p, spec):
    if 'colors' in spec and p['color'] not in spec['colors']:
        return False
    if p['color'] in spec.get('not_colors', []):
        return False
    if 'max_price' in spec and p['price']['amount'] > spec['max_price']:
        return False
    if 'min_price' in spec and p['price']['amount'] < spec['min_price']:
        return False
    if 'min_rating' in spec and (p['rating']['average'] is None or p['rating']['average'] < spec['min_rating']):
        return False
    return True


def grade(p, spec):
    if not ok_constraints(p, spec):
        return 0
    g = 3 if p['product_type'] in spec.get('types', [p['product_type']]) else 0
    if g and 'audiences' in spec and p['audience'] not in spec['audiences']:
        g = 1
    if g and 'text' in spec:
        blob = f"{p['name']} {p['description']}".lower()
        if not any(t in blob for t in spec['text']) and p['pattern'] not in spec.get('patterns', []):
            g = 2
    return g


def ndcg(grades, k=10):
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades[:k]))
    ideal = sum((2 ** 3 - 1) / math.log2(i + 2) for i in range(k))
    return dcg / ideal


def main():
    show = '--show' in sys.argv
    index_dir = '/nonexistent' if '--no-semantic' in sys.argv else None
    t = time.time()
    catalog = Catalog.load(HERE.parent / 'data/products.json', index_dir=index_dir)
    print(f'load {time.time() - t:.1f}s semantic={catalog.embedder is not None}')
    name = next((a for a in sys.argv[1:] if a.endswith('.json')), 'queries.json')
    cases = json.loads((HERE / name).read_text())
    scores, latencies = {}, []
    for case in cases:
        args = {'query': case['query'], 'limit': 10, 'include_recommendations': case['cat'] == 'rec'}
        t = time.perf_counter()
        out = catalog.search(args)
        latencies.append((time.perf_counter() - t) * 1000)
        prods = [catalog.products[catalog.index_of[r['id']]] for r in out['results']]
        cat = case['cat']
        if cat == 'irrelevant':
            s = 1.0 if not prods else 0.0
        elif cat == 'mixed':
            g_lists = [[grade(p, {**c, **{k: v for k, v in case.items() if k in ('max_price',)}})
                        for p in prods] for c in case['choices']]
            best = [max(gs) if gs else 0 for gs in zip(*g_lists)] if prods else []
            coverage = sum(any(g >= 2 for g in gs) for gs in g_lists) / len(g_lists)
            s = 0.5 * coverage + 0.5 * ndcg(best)
        else:
            gs = [grade(p, case) for p in prods]
            s = ndcg(gs)
            if cat == 'rec':
                rec_spec = {'types': case['rec_types']}
                if 'rec_max_price' in case:
                    rec_spec['max_price'] = case['rec_max_price']
                rg = [grade(catalog.products[catalog.index_of[r['id']]], rec_spec) for r in out['recommendations']]
                s = 0.5 * s + 0.5 * ndcg(rg, 5)
        scores.setdefault(cat, []).append(s)
        flag = '' if s >= 0.8 else '  <-- low'
        print(f'{s:5.2f} [{cat}] {case["query"]}{flag}')
        if show or s < 0.8:
            for p in prods[:10]:
                print(f"        {p['product_type']:<16} {p['color']:<14} {p['price']['amount']:>5} "
                      f"{p['audience'][:14]:<14} {p['name'][:30]} | {p['description'][:50]}")
            for r in out['recommendations']:
                p = catalog.products[catalog.index_of[r['id']]]
                print(f"   REC  {p['product_type']:<16} {p['color']:<14} {p['price']['amount']:>5} {p['name'][:30]}")
    print()
    for cat, vals in scores.items():
        print(f'{cat:<11} {sum(vals) / len(vals):.3f} (n={len(vals)})')
    latencies.sort()
    print(f'latency p50 {latencies[len(latencies) // 2]:.1f} ms, p95 {latencies[int(len(latencies) * 0.95)]:.1f} ms')


if __name__ == '__main__':
    main()
