"""Replace Git LFS pointer files with their real content (for builders that clone without LFS).

python scripts/fetch_lfs.py

For each large file that is still an LFS pointer, download it from LFS_BASE_URL (GitHub's media
endpoint for this public repository by default), verify the SHA-256 and size recorded in the
pointer, then swap it in. Files that are already real are left alone, so this is a no-op locally.
"""
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ['data/products.json', 'index/embeddings.npy', 'index/doc_rows.npy']
BASE = os.getenv('LFS_BASE_URL', 'https://media.githubusercontent.com/media/hharshhsaini/ShopSense/main')


def pointer(path):
    head = path.read_bytes()[:200] if path.stat().st_size < 1024 else b''
    if not head.startswith(b'version https://git-lfs'):
        return None
    fields = dict(line.split(' ', 1) for line in head.decode().splitlines() if ' ' in line)
    return fields['oid'].removeprefix('sha256:').strip(), int(fields['size'])


def main():
    for rel in FILES:
        path = ROOT / rel
        info = pointer(path)
        if info is None:
            print(f'{rel}: present')
            continue
        oid, size = info
        tmp = path.with_suffix(path.suffix + '.part')
        digest = hashlib.sha256()
        with urllib.request.urlopen(f'{BASE}/{rel}', timeout=300) as response, open(tmp, 'wb') as out:
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != oid or tmp.stat().st_size != size:
            tmp.unlink()
            sys.exit(f'{rel}: downloaded content does not match the LFS pointer')
        tmp.replace(path)
        print(f'{rel}: fetched {size} bytes, sha256 verified')


if __name__ == '__main__':
    main()
