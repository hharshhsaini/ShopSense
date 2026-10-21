"""Offline embedding build: python build_index.py [catalog] [out_dir].

Encodes one document per distinct product text with a fixed fastembed model and
stores float16 vectors plus a row map, so the server never embeds the catalog.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
MODEL_NAME = 'BAAI/bge-small-en-v1.5'
MODEL_DIR = ROOT / '.models'


def product_document(p):
    """Catalog facts only; synthetic reviews are left out on purpose."""
    return (f"{p['name']}. {p['description']} Type: {p['product_type']} ({p['category']}). "
            f"Colour: {p['color']}. Pattern: {p['pattern']}. For: {p['audience']}, {p['section']}.")


def main(catalog_path=ROOT / 'data/products.json', out_dir=ROOT / 'index'):
    from fastembed import TextEmbedding
    catalog_path, out_dir = Path(catalog_path), Path(out_dir)
    raw = catalog_path.read_bytes()
    products = sorted(json.loads(raw), key=lambda p: p['id'])
    docs = [product_document(p) for p in products]
    unique = sorted(set(docs))
    position = {d: i for i, d in enumerate(unique)}
    print(f'{len(products)} products, {len(unique)} distinct documents', flush=True)
    model = TextEmbedding(MODEL_NAME, cache_dir=str(MODEL_DIR), threads=os.cpu_count())
    start, vectors = time.time(), []
    for i, v in enumerate(model.embed(unique, batch_size=64)):
        vectors.append(v)
        if i % 10000 == 0:
            print(f'{i} {time.time() - start:.0f}s', flush=True)
    matrix = np.asarray(vectors, dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    out_dir.mkdir(exist_ok=True)
    np.save(out_dir / 'embeddings.npy', matrix.astype(np.float16))
    np.save(out_dir / 'doc_rows.npy', np.array([position[d] for d in docs], dtype=np.int32))
    (out_dir / 'meta.json').write_text(json.dumps({
        'model': MODEL_NAME, 'dim': int(matrix.shape[1]), 'normalized': True, 'metric': 'cosine',
        'products': len(products), 'documents': len(unique), 'order': 'products sorted by id',
        'catalog_sha256': hashlib.sha256(raw).hexdigest(),
        'build_seconds': round(time.time() - start, 1)}, indent=2))
    print('done', time.time() - start, flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
