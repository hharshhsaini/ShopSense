"""Catalog search behind the search_products tool.

Pipeline per request:
  1. validate arguments against the published schema;
  2. exact explicit filters as numpy masks (empty queries stop here: exact
     catalog-filtered page in the requested order);
  3. parse the query into choices with hard constraints (garment concept,
     colour, audience, budget, rating, exclusions);
  4. score candidates with BM25F over catalog fields plus precomputed
     embeddings, catalog-attribute bonuses and a small rating prior;
  5. pool mixed choices, sort, paginate, then build complementary
     recommendations when requested.
"""
import hashlib
import json
import logging
import math
import re
import threading
from collections import Counter, OrderedDict
from functools import lru_cache
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator, ValidationError
from scipy import sparse

import lexicon as L
from query_parser import (CONCEPT_TERMS, GARMENT_NOUNS, Choice, Vocabulary, normalize, parse, stem,
                          tokenize)

ROOT = Path(__file__).resolve().parent
INPUT_SCHEMA = json.loads((ROOT / 'schemas/input.schema.json').read_text())
OUTPUT_SCHEMA = json.loads((ROOT / 'schemas/output.schema.json').read_text())
VALIDATOR = Draft202012Validator(INPUT_SCHEMA)
STRING_FILTERS = ('category', 'product_type', 'color', 'audience', 'section', 'pattern')
ALL_CONCEPTS = {**L.CONCEPTS, **L.EXTRA_COMPLEMENT_CONCEPTS}
FIELD_WEIGHTS = {'head': 3.0, 'name': 1.5, 'type': 2.0, 'desc': 1.0, 'attrs': 0.6}
K1, B = 1.2, 0.75
MAX_RELEVANT = 500
CLAUSE = re.compile(r'\b(?:in|with|made|from|for|that|which|containing|featuring)\b|[;(:]')
log = logging.getLogger(__name__)


def validate_arguments(arguments):
    # Reject non-JSON floating point values even when called directly from Python.
    json.dumps(arguments, allow_nan=False)
    try:
        VALIDATOR.validate(arguments)
    except ValidationError as exc:
        raise ValueError(exc.message) from exc
    filters = arguments.get('filters', {})
    if any(not filters[k].strip() for k in STRING_FILTERS if k in filters):
        raise ValueError('String filters cannot be blank')
    if filters.get('min_price', 0) > filters.get('max_price', math.inf):
        raise ValueError('min_price cannot exceed max_price')


@lru_cache(maxsize=2048)
def tokens(text):
    return tuple(re.findall(r'\w+', text.casefold()))


def description_head(description):
    """Clause naming the garment, e.g. '5-pocket jeans' from '5-pocket jeans in denim ...'."""
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', description or '') if s.strip()][:3]
    first = None
    for sentence in sentences:
        clause = CLAUSE.split(sentence.rstrip('.'), maxsplit=1)[0]
        toks = tokenize(clause)
        first = first if first is not None else toks
        nouns = [t for t in toks if t in GARMENT_NOUNS]
        if nouns:
            return toks, nouns[-1]
    return first or [], None


class Catalog:
    def __init__(self, products, index_dir=None, catalog_sha256=None):
        self.products = sorted(products, key=lambda p: p['id'])
        if len({p['id'] for p in self.products}) != len(self.products):
            raise ValueError('Catalog contains duplicate product IDs')
        self.ids = [p['id'] for p in self.products]
        self.index_of = {pid: i for i, pid in enumerate(self.ids)}
        n = self.n = len(self.products)
        self.price = np.array([p['price']['amount'] for p in self.products], dtype=np.float64)
        self.rating = np.array([np.nan if p['rating']['average'] is None else p['rating']['average']
                                for p in self.products], dtype=np.float64)
        self.count = np.array([p['rating']['count'] for p in self.products], dtype=np.int64)
        self.codes, self.values = {}, {}
        for key in STRING_FILTERS:
            labels = [str(p.get(key) or '').strip().casefold() for p in self.products]
            vocab = {v: i for i, v in enumerate(sorted(set(labels)))}
            self.values[key] = vocab
            self.codes[key] = np.array([vocab[v] for v in labels], dtype=np.int32)
        self.raw_values = {key: sorted({str(p.get(key) or '') for p in self.products}) for key in STRING_FILTERS}
        self._build_orders()
        self._build_text_index()
        self.quality = np.where(np.isnan(self.rating), 0.0, (np.nan_to_num(self.rating, nan=3.0) - 3.0) / 2.0) \
            * np.minimum(self.count, 5) / 5.0
        self._mask_cache, self._lock = {}, threading.Lock()
        self._results = OrderedDict()
        self.adult = (self.audience_mask('women') | self.audience_mask('men')).astype(np.float64)
        self.embedder = self.embeddings = self.doc_rows = None
        if index_dir is not None:
            self._load_semantic(Path(index_dir), catalog_sha256)

    @classmethod
    def load(cls, path, index_dir=None):
        raw = Path(path).read_bytes()
        index_dir = ROOT / 'index' if index_dir is None else index_dir
        return cls(json.loads(raw), index_dir=index_dir, catalog_sha256=hashlib.sha256(raw).hexdigest())

    # ------------------------------------------------------------------ indexes
    def _build_orders(self):
        idx = np.arange(self.n)
        rated = ~np.isnan(self.rating)
        self.orders = {('id', 'asc'): idx, ('id', 'desc'): idx[::-1].copy()}
        for name, values in (('price', self.price), ('review_count', self.count.astype(np.float64))):
            self.orders[(name, 'asc')] = np.lexsort((idx, values))
            self.orders[(name, 'desc')] = np.lexsort((idx, -values))
        r = np.nan_to_num(self.rating, nan=0.0)
        for order, sign in (('asc', 1), ('desc', -1)):
            ranked = np.lexsort((idx, sign * r, ~rated))
            self.orders[('rating', order)] = ranked
        self.rank = {key: np.argsort(order, kind='stable') for key, order in self.orders.items()}

    def _build_text_index(self):
        fields = {f: [] for f in FIELD_WEIGHTS}
        nouns = []
        for p in self.products:
            head, noun = description_head(p['description'])
            nouns.append(noun)
            fields['head'].append(head)
            fields['name'].append(tokenize(p['name']))
            fields['type'].append(tokenize(f"{p['product_type']} {p['category']}"))
            fields['desc'].append(tokenize(p['description'] or ''))
            fields['attrs'].append(tokenize(f"{p['color']} {p['pattern']} {p['audience']} {p['section']}"))
        term_ids, df = {}, Counter()
        for i in range(self.n):
            seen = set()
            for f in fields:
                for t in fields[f][i]:
                    if t not in term_ids:
                        term_ids[t] = len(term_ids)
                    seen.add(t)
            df.update(seen)
        V = len(term_ids)
        idf = np.zeros(V, dtype=np.float32)
        for t, j in term_ids.items():
            idf[j] = math.log(1 + (self.n - df[t] + 0.5) / (df[t] + 0.5))
        total = None
        presence_fields = None
        for f, weight in FIELD_WEIGHTS.items():
            rows, cols, vals = [], [], []
            lengths = np.array([len(x) for x in fields[f]], dtype=np.float32)
            avg = max(float(lengths.mean()), 1.0)
            for i, toks in enumerate(fields[f]):
                if not toks:
                    continue
                norm = K1 * (1 - B + B * lengths[i] / avg)
                for t, tf in Counter(toks).items():
                    rows.append(i)
                    cols.append(term_ids[t])
                    vals.append(weight * tf * (K1 + 1) / (tf + norm))
            m = sparse.csr_matrix((np.array(vals, dtype=np.float32), (rows, cols)), shape=(self.n, V))
            total = m if total is None else total + m
            if f in ('head', 'name', 'desc', 'type'):
                b = (m > 0).astype(np.float32)
                presence_fields = b if presence_fields is None else presence_fields + b
        self.term_ids = term_ids
        self.weights = (total @ sparse.diags(idf)).tocsc()
        self.presence = (presence_fields > 0).astype(np.float32).tocsc()
        self.vocab = Vocabulary(dict(df), {tok for toks in fields['desc'] for tok in toks})
        noun_vocab = {t: i + 1 for i, t in enumerate(sorted(GARMENT_NOUNS))}
        self.noun_ids = noun_vocab
        self.noun = np.array([noun_vocab.get(x, 0) for x in nouns], dtype=np.int32)

    def _load_semantic(self, index_dir, catalog_sha256):
        meta_path = index_dir / 'meta.json'
        if not meta_path.exists():
            log.warning('No semantic index at %s; using lexical ranking only', index_dir)
            return
        meta = json.loads(meta_path.read_text())
        if meta.get('products') != self.n or (catalog_sha256 and meta.get('catalog_sha256') != catalog_sha256):
            log.warning('Semantic index does not match this catalog; using lexical ranking only')
            return
        try:
            from fastembed import TextEmbedding
            embeddings = np.load(index_dir / 'embeddings.npy').astype(np.float32)
            doc_rows = np.load(index_dir / 'doc_rows.npy')
            self.embedder = TextEmbedding(meta['model'], cache_dir=str(ROOT / '.models'),
                                          local_files_only=(ROOT / '.models').exists())
            self.embeddings, self.doc_rows = embeddings, doc_rows
            self._embed_query('warm up')
        except Exception:
            log.exception('Embedding model unavailable; using lexical ranking only')
            self.embedder = self.embeddings = self.doc_rows = None

    @lru_cache(maxsize=4096)
    def _embed_query(self, text):
        vector = next(iter(self.embedder.query_embed([text])))
        vector = np.asarray(vector, dtype=np.float32)
        return vector / (np.linalg.norm(vector) or 1.0)

    def semantic_scores(self, text):
        if self.embedder is None or not text.strip():
            return None
        return (self.embeddings @ self._embed_query(text))[self.doc_rows]

    def warm(self):
        """Build every reusable mask once so first requests do not pay for it."""
        for name in ALL_CONCEPTS:
            self.concept_mask(name)
            self.concept_core(name)
        for audience in ('women', 'men', 'kids', 'boys', 'girls', 'baby', 'teen', 'maternity', 'plus'):
            self.audience_mask(audience)
        self.search({'query': 'black dress and white sneakers', 'include_recommendations': True})
        self._results.clear()

    # ------------------------------------------------------------------ masks
    def _cached(self, key, build):
        mask = self._mask_cache.get(key)
        if mask is None:
            mask = build()
            mask.setflags(write=False)
            with self._lock:
                self._mask_cache[key] = mask
        return mask

    def value_mask(self, key, values):
        """Products whose field equals any of the given catalog values (case-insensitive)."""
        values = tuple(sorted({v.strip().casefold() for v in values}))
        def build():
            codes = [self.values[key][v] for v in values if v in self.values[key]]
            return np.isin(self.codes[key], codes)
        return self._cached((key, values), build)

    def filter_mask(self, filters):
        mask = np.ones(self.n, dtype=bool)
        for key in STRING_FILTERS:
            if key in filters:
                mask &= self.value_mask(key, [filters[key]])
        if 'min_price' in filters:
            mask &= self.price >= filters['min_price']
        if 'max_price' in filters:
            mask &= self.price <= filters['max_price']
        if 'min_rating' in filters:
            mask &= self.rating >= filters['min_rating']  # NaN compares False: null ratings fail
        if filters.get('min_review_count', 0) > 0:
            mask &= self.count >= filters['min_review_count']
        return mask

    def concept_mask(self, name):
        def build():
            _terms, types, nouns, cats = ALL_CONCEPTS[name]
            mask = self.value_mask('product_type', types) if types else np.zeros(self.n, dtype=bool)
            noun_codes = [self.noun_ids[stem(x)] for x in nouns if stem(x) in self.noun_ids]
            by_noun = np.isin(self.noun, noun_codes) if noun_codes else np.zeros(self.n, dtype=bool)
            if cats:
                by_noun &= self.value_mask('category', cats)
                if not types and not nouns:
                    by_noun = self.value_mask('category', cats).copy()
            if name == 'jeans':
                by_noun |= self.value_mask('product_type', ['Trousers', 'Shorts']) & \
                    self.value_mask('pattern', ['Denim']) & self.term_mask(('jeans', 'denim'))
            return mask | by_noun
        return self._cached(('concept', name), build)

    def concept_core(self, name):
        """Products matching a concept by both type and head noun (strongest evidence)."""
        def build():
            _terms, types, nouns, _cats = ALL_CONCEPTS[name]
            noun_codes = [self.noun_ids[stem(x)] for x in nouns if stem(x) in self.noun_ids]
            by_type = self.value_mask('product_type', types) if types else None
            by_noun = np.isin(self.noun, noun_codes) if noun_codes else None
            if by_type is None and by_noun is None:
                return self.concept_mask(name).copy()
            if by_type is None or by_noun is None:
                return (by_type if by_noun is None else by_noun).copy()
            return by_type & by_noun
        return self._cached(('core', name), build)

    def audience_mask(self, audience):
        def build():
            aud, sec = (lambda vs: self.value_mask('audience', vs)), (lambda vs: self.value_mask('section', vs))
            kids = aud(L.KIDS_AUDIENCES) | sec(['Kids Sports'])
            baby = aud(L.BABY_AUDIENCES)
            if audience == 'women':
                return aud(L.WOMEN_AUDIENCES) | sec(['Ladies H&M Sport'])
            if audience == 'men':
                return aud(L.MEN_AUDIENCES) | sec(['Men H&M Sport'])
            if audience == 'kids':
                return kids
            if audience == 'boys':
                return (kids | baby) & sec(L.BOY_SECTIONS | L.UNISEX_KIDS_SECTIONS)
            if audience == 'girls':
                return (kids | baby) & sec(L.GIRL_SECTIONS | L.UNISEX_KIDS_SECTIONS)
            if audience == 'baby':
                return baby
            if audience == 'teen':
                return aud(['Divided', 'Children Sizes 134-170'])
            if audience == 'maternity':
                return sec(['Mama'])
            if audience == 'plus':
                return sec(['H&M+'])
            return np.ones(self.n, dtype=bool)
        return self._cached(('audience', audience), build)

    def audience_family(self, index):
        p = self.products[index]
        for family in ('men', 'women', 'baby', 'boys', 'girls', 'kids'):
            if self.audience_mask(family)[index]:
                if family in ('boys', 'girls') and p['section'] in L.UNISEX_KIDS_SECTIONS:
                    return 'kids'
                return family
        return None

    def term_mask(self, terms):
        cols = [self.term_ids[t] for t in terms if t in self.term_ids]
        if not cols:
            return np.zeros(self.n, dtype=bool)
        return np.asarray(self.presence[:, cols].sum(axis=1)).ravel() > 0

    def lexical_scores(self, weighted_terms):
        cols, w = [], []
        for t, weight in weighted_terms.items():
            if t in self.term_ids:
                cols.append(self.term_ids[t])
                w.append(weight)
        if not cols:
            return np.zeros(self.n, dtype=np.float32)
        return np.asarray(self.weights[:, cols] @ np.array(w, dtype=np.float32)).ravel()

    # ------------------------------------------------------------------ choices
    def choice_mask(self, choice, filters, parsed, base):
        mask = base.copy()
        if choice.concepts and 'product_type' not in filters:
            concept = np.zeros(self.n, dtype=bool)
            for name in choice.concepts:
                concept |= self.concept_mask(name)
            if (mask & concept).any() or 'category' not in filters:
                mask &= concept
        if choice.colors and 'color' not in filters:
            mask &= self.value_mask('color', choice.colors)
        if choice.exclude_colors:
            mask &= ~self.value_mask('color', choice.exclude_colors)
        for name in choice.exclude_concepts - set(choice.concepts):
            mask &= ~self.concept_core(name)
        if choice.exclude_terms:
            mask &= ~self.term_mask(sorted({stem(t) for t in choice.exclude_terms}))
        if choice.audience and 'audience' not in filters and 'section' not in filters:
            mask &= self.audience_mask(choice.audience)
        lo = filters.get('min_price', 0)
        hi = filters.get('max_price', math.inf)
        qlo = choice.min_price if choice.min_price is not None else 0
        qhi = choice.max_price if choice.max_price is not None else math.inf
        if max(lo, qlo) <= min(hi, qhi):  # explicit filters win over conflicting query budgets
            if choice.min_price is not None:
                mask &= self.price >= qlo
            if choice.max_price is not None:
                mask &= self.price <= qhi
        if parsed.min_rating is not None and parsed.min_rating >= filters.get('min_rating', 0):
            mask &= self.rating >= parsed.min_rating
        if parsed.min_reviews:
            mask &= self.count >= parsed.min_reviews
        return mask

    def score_choice(self, choice, parsed, candidates, context=''):
        """Relevance scores for candidate indices (higher is better)."""
        terms = {}
        for t in choice.content:
            terms[t] = terms.get(t, 0) + 1.0
        for t in choice.style_terms:
            terms[t] = terms.get(t, 0) + 0.6
        for group in choice.pattern_terms + choice.material_terms:
            for t in group:
                terms[t] = max(terms.get(t, 0), 1.0)
        for t in choice.tokens:
            if t in CONCEPT_TERMS:  # garment already rewarded via type/noun bonuses
                terms[t] = max(terms.get(t, 0), 0.4)
        lex = self.lexical_scores(terms)[candidates] if terms else np.zeros(len(candidates), np.float32)
        top = float(lex.max()) if len(lex) else 0.0
        lex_n = lex / top if top > 0 else lex
        sem_text = self.semantic_text(choice, context)
        sem_all = self.semantic_scores(sem_text)
        score = np.zeros(len(candidates), dtype=np.float64)
        if sem_all is not None:
            sem = sem_all[candidates].astype(np.float64)
            floor = float(np.median(sem)) if len(sem) > 20 else float(sem.min()) - 0.05
            span = max(float(sem.max()) - floor, 1e-6)
            score += 0.5 * np.clip((sem - floor) / span, 0, 1) + 0.35 * lex_n
        else:
            score += 0.85 * lex_n
        if choice.concepts:
            core = np.zeros(self.n, dtype=bool)
            loose = np.zeros(self.n, dtype=bool)
            for name in choice.concepts:
                core |= self.concept_core(name)
                loose |= self.concept_mask(name)
            score += 0.25 * core[candidates] + 0.1 * loose[candidates]
        if choice.color_primary:
            score += 0.12 * self.value_mask('color', choice.color_primary)[candidates]
        groups = choice.pattern_terms + choice.material_terms
        if groups:
            hit = np.zeros(len(candidates))
            for group in groups:
                hit += self.term_mask(group)[candidates]
            if choice.patterns:
                hit = np.maximum(hit, self.value_mask('pattern', choice.patterns)[candidates] * len(choice.pattern_terms))
            score += 0.4 * hit / len(groups)
        if choice.style_terms:
            hit = np.zeros(len(candidates))
            for t in choice.style_terms:
                hit += self.term_mask([t])[candidates]
            score += 0.2 * hit / len(choice.style_terms)
        if choice.occasions:
            types = self.occasion_types(choice.occasions)
            if types:  # with a named garment this only separates garments of that kind
                score += (0.12 if choice.concepts else 0.2) * self.value_mask('product_type', types)[candidates]
        if not choice.audience:
            score += 0.18 * self.adult[candidates]
        score += (0.12 if parsed.prefer_rating else 0.03) * self.quality[candidates]
        if parsed.prefer_cheap or parsed.prefer_expensive:
            prices = self.price[candidates]
            span = max(prices.max() - prices.min(), 1.0)
            rel = (prices - prices.min()) / span
            score += 0.3 * ((1 - rel) if parsed.prefer_cheap else rel)
        return score

    @staticmethod
    def semantic_text(choice, context=''):
        text = re.sub(r'\b(?:inr|rs|rupees?|under|below|each|over|above|cheap|cheapest|affordable|budget|'
                      r'inexpensive|expensive|premium|luxury|highly|top|best|well|rated|reviewed|stars?)\b|\d+',
                      ' ', choice.text)
        text = ' '.join(L.READABLE.get(w, w) for w in text.split())
        hints = [L.OCCASIONS[o][1] for o in choice.occasions if L.OCCASIONS[o][1] not in ('gift', 'outfit')]
        if hints and not choice.concepts:
            text = f"{text}. {'; '.join(hints)}"
        return re.sub(r'\s+', ' ', f'{text} {context}').strip()

    def rank_choice(self, choice, parsed, filters, base):
        mask = self.choice_mask(choice, filters, parsed, base)
        if not choice.concepts:
            mask &= self._evidence_mask(choice)
            types = self.occasion_types(choice.occasions)
            if types and 'product_type' not in filters:
                by_occasion = mask & self.value_mask('product_type', types)
                if by_occasion.any():
                    mask = by_occasion
        elif choice.occasions and 'product_type' not in filters:
            # "shoes for walking" -> trainers/flats; a no-op when every candidate already fits.
            types = self.occasion_types(choice.occasions)
            fitting = mask & self.value_mask('product_type', types) if types else mask
            if np.count_nonzero(fitting) >= 5:
                mask = fitting
        # Named patterns/materials and "highly rated" become filters when the catalog can satisfy them.
        for group in choice.pattern_terms + choice.material_terms:
            wanted = self.term_mask(group)
            if choice.patterns and group in choice.pattern_terms:
                wanted = wanted | self.value_mask('pattern', choice.patterns)
            if np.count_nonzero(mask & wanted) >= 5:
                mask &= wanted
        # Specific descriptive words ("dinosaur pyjamas", "laptop bag", "cropped hoodie") narrow a garment.
        if choice.concepts:
            for word in dict.fromkeys(choice.content + choice.style_terms):
                df = self.vocab.doc_freq.get(word, 0)
                if 0 < df < 0.05 * self.n:
                    narrowed = mask & self.term_mask([word])
                    if np.count_nonzero(narrowed) >= 3:
                        mask = narrowed
        if parsed.prefer_rating and parsed.min_rating is None:
            rated = mask & (self.rating >= 4.0)
            if np.count_nonzero(rated) >= 5:
                mask = rated
        candidates = np.flatnonzero(mask)
        if not len(candidates):
            return candidates, np.zeros(0)
        scores = self.score_choice(choice, parsed, candidates)
        order = np.lexsort((candidates, -scores))
        candidates, scores = candidates[order], scores[order]
        keep = scores >= max(scores[0] * 0.55, scores[0] - 0.6)
        keep[:10] = True
        candidates, scores = candidates[keep][:MAX_RELEVANT], scores[keep][:MAX_RELEVANT]
        return self._diversify(candidates, scores)

    @staticmethod
    def occasion_types(occasions):
        """Product types for occasion words: a concrete use, narrowed by weather/mood modifiers."""
        sets = [(o, set(L.OCCASIONS[o][0])) for o in occasions if L.OCCASIONS[o][0]]
        uses = [s for o, s in sets if o not in L.MODIFIER_OCCASIONS]
        mods = [s for o, s in sets if o in L.MODIFIER_OCCASIONS]
        if not uses and not mods:
            return set()
        types = set().union(*uses) if uses else mods.pop(0)
        for m in mods:
            if types & m:
                types &= m
        return types

    def _evidence_mask(self, choice):
        """Without a garment concept, require catalog text evidence for specific words.

        When the query already carries a shopping signal (occasion, colour, pattern,
        material, style or audience), leftover words only influence ranking.
        """
        signal = (choice.occasions or choice.colors or choice.patterns or choice.pattern_terms
                  or choice.material_terms or choice.style_terms or choice.audience)
        if not choice.content or signal:
            return np.ones(self.n, dtype=bool)
        mask = np.ones(self.n, dtype=bool)
        for t in choice.content:
            mask &= self.term_mask([t])
        return mask

    def _diversify(self, candidates, scores):
        """Gently demote repeated colour variants of the same article name and description."""
        if len(candidates) < 3:
            return candidates, scores
        head = min(len(candidates), 200)
        seen, adjusted = Counter(), scores[:head].copy()
        for k in range(head):
            p = self.products[candidates[k]]
            key = (p['name'].casefold(), p['description'])
            adjusted[k] -= 0.08 * seen[key]
            seen[key] += 1
        order = np.lexsort((candidates[:head], -adjusted))
        return (np.concatenate([candidates[:head][order], candidates[head:]]),
                np.concatenate([adjusted[order], scores[head:]]))

    # ------------------------------------------------------------------ search
    def search(self, arguments):
        validate_arguments(arguments)
        key = json.dumps(arguments, sort_keys=True)
        with self._lock:
            cached = self._results.get(key)
            if cached is not None:
                self._results.move_to_end(key)
        if cached is None:
            cached = self._search(arguments)
            with self._lock:
                self._results[key] = cached
                while len(self._results) > 2048:
                    self._results.popitem(last=False)
        return {'results': [dict(r) for r in cached['results']],
                'recommendations': [dict(r) for r in cached['recommendations']]}

    def _search(self, arguments):
        query = arguments.get('query', '').strip()
        filters = arguments.get('filters', {})
        sort_by = arguments.get('sort_by', 'relevance')
        order = arguments.get('sort_order', 'desc')
        offset, limit = int(arguments.get('offset', 0)), int(arguments.get('limit', 10))
        base = self.filter_mask(filters)
        parsed = None
        if not query:
            if sort_by == 'relevance':
                sort_by, order = 'id', 'asc'
            ranked = self.orders[(sort_by, order)]
            page = ranked[base[ranked]][offset:offset + limit]
        else:
            try:
                parsed = parse(query, self.vocab)
                relevant = self.relevant(parsed, filters, base)
            except Exception:  # degrade to plain lexical retrieval, never fail a valid call
                log.exception('Query interpretation failed; using lexical fallback')
                parsed, relevant = None, self.lexical_fallback(query, base)
            if sort_by == 'relevance':
                ordered = relevant if order == 'desc' else relevant[::-1]
            else:
                ordered = relevant[np.argsort(self.rank[(sort_by, order)][relevant], kind='stable')]
            page = ordered[offset:offset + limit]
        results = [{'id': self.ids[i]} for i in page]
        recommendations = []
        if results and arguments.get('include_recommendations', False):
            recommendations = self.recommend_for(page, parsed, filters)
        return {'results': results, 'recommendations': recommendations}

    def relevant(self, parsed, filters, base):
        """Pooled relevant products for all primary choices, best first."""
        if parsed.abstain:
            return np.zeros(0, dtype=np.int64)
        lists = [self.rank_choice(c, parsed, filters, base)[0] for c in parsed.choices]
        lists = [x for x in lists if len(x)]
        if len(lists) <= 1:
            return lists[0] if lists else np.zeros(0, dtype=np.int64)
        pooled, seen = [], set()
        for k in range(max(len(x) for x in lists)):
            for x in lists:
                if k < len(x) and x[k] not in seen:
                    seen.add(int(x[k]))
                    pooled.append(int(x[k]))
        return np.array(pooled, dtype=np.int64)

    def lexical_fallback(self, query, base):
        """All-terms lexical match over the filtered catalog, best BM25F first."""
        terms = [t for t in tokenize(query) if t in self.term_ids]
        if not terms:
            return np.zeros(0, dtype=np.int64)
        mask = base.copy()
        for t in set(terms):
            mask &= self.term_mask([t])
        candidates = np.flatnonzero(mask)
        scores = self.lexical_scores({t: 1.0 for t in terms})[candidates]
        return candidates[np.lexsort((candidates, -scores))][:MAX_RELEVANT]

    # ------------------------------------------------------------------ recommendations
    def recommend(self, results, arguments):
        """Complementary products for a result page (kept for API compatibility)."""
        page = [self.index_of[r['id']] for r in results]
        query = arguments.get('query', '').strip()
        parsed = parse(query, self.vocab) if query else None
        return self.recommend_for(page, parsed, arguments.get('filters', {}))

    def concept_of(self, index):
        p = self.products[index]
        noun = self.noun[index]
        for name in L.COMPLEMENTS:
            if self.concept_core(name)[index]:
                return name
        for name in L.COMPLEMENTS:
            if self.concept_mask(name)[index]:
                return name
        return None

    def recommend_for(self, page, parsed, filters):
        if not len(page):
            return []
        anchor = int(page[0])
        primary = set(int(i) for i in page)
        explicit = parsed.complements if parsed else []
        if parsed and parsed.choices:
            primary_choice = parsed.choices[0]
        else:
            primary_choice = Choice(text='')
        audience = primary_choice.audience or self.audience_family(anchor)
        if explicit:
            wanted = explicit
        else:
            concept = next((c for c in primary_choice.concepts if c in L.COMPLEMENTS), None) \
                or self.concept_of(anchor)
            names = [c for c in L.COMPLEMENTS.get(concept, ['bag', 'sunglasses', 'scarf'])
                     if c not in primary_choice.concepts and not (c == 'tie' and audience == 'women')]
            wanted = [Choice(text=c, tokens=[c], concepts=[c], complement=True,
                             min_price=primary_choice.min_price, max_price=primary_choice.max_price)
                      for c in names]
        anchor_p = self.products[anchor]
        context = f"to go with a {anchor_p['color'].lower()} {anchor_p['product_type'].lower()}"
        pools = []
        for choice in wanted:
            if not choice.concepts and not choice.content:
                continue
            fake = parsed if parsed is not None else _NEUTRAL
            mask = self.choice_mask(choice, {}, fake if explicit else _NEUTRAL, np.ones(self.n, dtype=bool))
            if audience and not choice.audience:
                fam = self.audience_mask(audience)
                if audience in ('women', 'men'):
                    fam = fam | self.value_mask('audience', ['Ladies Accessories' if audience == 'women'
                                                             else 'Menswear'])
                if (mask & fam).any():
                    mask &= fam
            mask[list(primary)] = False
            if not choice.concepts:
                mask &= self._evidence_mask(choice)
            candidates = np.flatnonzero(mask)
            if not len(candidates):
                continue
            scores = self.score_choice(choice, fake if explicit else _NEUTRAL, candidates, context)
            colors = self.codes['color'][candidates]
            same = colors == self.codes['color'][anchor]
            neutral = self.value_mask('color', L.NEUTRAL_COLORS)[candidates]
            if not choice.colors:
                scores += 0.08 * same + 0.05 * neutral
            ranked = candidates[np.lexsort((candidates, -scores))][:20]
            ranked, _ = self._diversify(ranked, np.linspace(1, 0, len(ranked)))
            pools.append((choice, ranked))
        recs, used = [], set(primary)
        depth = 0
        while len(recs) < 5 and pools and depth < 20:
            for choice, ranked in pools:
                if depth < len(ranked) and len(recs) < 5 and int(ranked[depth]) not in used:
                    i = int(ranked[depth])
                    used.add(i)
                    recs.append({'id': self.ids[i], 'for_product_id': self.ids[anchor],
                                 'reason': self.reason(i, anchor)})
            depth += 1
        return recs

    def reason(self, rec, anchor):
        r, a = self.products[rec], self.products[anchor]
        text = (f"{r['product_type']} in {r['color'].lower()} to pair with this "
                f"{a['color'].lower()} {a['product_type'].lower()}")
        if r['color'] == a['color']:
            text += ' in a matching colour'
        elif r['color'] in L.NEUTRAL_COLORS:
            text += '; a neutral shade that coordinates easily'
        return (text + '.')[:300]


class _Neutral:
    min_rating = None
    min_reviews = None
    prefer_cheap = prefer_expensive = prefer_rating = False


_NEUTRAL = _Neutral()
