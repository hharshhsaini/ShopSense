"""Deterministic shopping-query interpretation.

Turns free text into primary choices, complementary choices and constraints.
Only vocabulary in lexicon.py and words seen in the catalog are recognized; the
parser never invents product facts.
"""
import gzip
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

import lexicon as L

WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


PHRASES = [(re.compile(pattern), repl, triggers) for pattern, repl, triggers in L.PHRASES]


@lru_cache(maxsize=200000)
def normalize(text):
    text = unicodedata.normalize('NFKC', text).casefold().replace('’', "'")
    text = text.replace('₹', ' inr ').replace('&', ' and ')
    for pattern, repl, triggers in PHRASES:
        if any(t in text for t in triggers):
            text = pattern.sub(repl, text)
    return text


@lru_cache(maxsize=65536)
def stem(word):
    if word in L.KEEP_PLURAL or len(word) <= 3 or not word.endswith('s'):
        return word
    if word.endswith(('sses', 'ches', 'shes', 'xes', 'zes')):
        return word[:-2]
    if word.endswith(('ss', 'us', 'is')):
        return word
    return word[:-1]


@lru_cache(maxsize=200000)
def tokenize(text):
    """Normalized, stemmed tokens for indexing and matching."""
    return tuple(stem(w.replace("'", '')) for w in WORD.findall(normalize(text)))


# Concept lookup: stemmed query word -> concept names.
CONCEPT_TERMS = {}
for _name, (_terms, _types, _nouns, _cats) in {**L.CONCEPTS, **L.EXTRA_COMPLEMENT_CONCEPTS}.items():
    for _term in _terms:
        if ' ' not in _term:
            CONCEPT_TERMS.setdefault(stem(_term), []).append(_name)
CONCEPT_PHRASES = [(t, n) for n, (ts, *_r) in L.CONCEPTS.items() for t in ts if ' ' in t]
GARMENT_NOUNS = {stem(n) for (_t, _ty, nouns, _c) in L.CONCEPTS.values() for n in nouns}
COLOR_WORDS = {stem(k): v for k, v in L.COLORS.items()}
PATTERN_WORDS = {stem(k): k for k in L.PATTERNS}
MATERIAL_WORDS = {stem(m): m for m in L.MATERIALS}
OCCASION_WORDS = {stem(k): k for k in L.OCCASIONS}
STYLE_WORDS = {stem(w) for w in L.STYLE_WORDS}
STOP = {stem(w) for w in L.STOPWORDS}
OFF_TOPIC = L.OFF_TOPIC  # matched against raw and stemmed query words; never stem the list ("news" -> "new")
NEGATION = {stem(w) for w in L.NEGATIONS}
KNOWN = (set(CONCEPT_TERMS) | set(COLOR_WORDS) | set(PATTERN_WORDS) | set(MATERIAL_WORDS)
         | set(OCCASION_WORDS) | STYLE_WORDS | STOP | {stem(w) for w in L.AUDIENCE_WORDS}
         | {'dark', 'light', 'pastel', 'neutral', 'bright', 'colourful', 'colorful', 'colour', 'color',
            'rated', 'rating', 'star', 'review', 'reviewed', 'top', 'popular', 'bestseller'})

CURRENCY = r'(?:inr|rs\.?|rupees?|₹|usd|\$)?'
NUMBER = r'(\d+(?:\.\d+)?)\s*(k)?'
PRICE_PATTERNS = [
    ('range', re.compile(rf'\b(?:between|from)\s+{CURRENCY}\s*{NUMBER}\s*{CURRENCY}\s*(?:and|to|-)\s*{CURRENCY}\s*{NUMBER}\s*{CURRENCY}')),
    ('range', re.compile(rf'{CURRENCY}\s*\b{NUMBER}\s*(?:-|to)\s*{CURRENCY}\s*{NUMBER}\s*(?:inr|rs\.?|rupees?)\b')),
    ('range', re.compile(rf'\b(?:inr|rs\.?|rupees?)\s*{NUMBER}\s*(?:-|to)\s*{CURRENCY}\s*{NUMBER}')),
    ('max', re.compile(rf'\b(?:under|below|beneath|less\s+than|lower\s+than|cheaper\s+than|up\s*to|upto|'
                       rf'max(?:imum)?(?:\s+of)?|at\s+most|no\s+more\s+than|not\s+more\s+than|within|'
                       rf'not\s+over|not\s+above|budget(?:\s+(?:of|is|around))?|spend(?:ing)?\s+(?:only\s+)?'
                       rf'(?:up\s+to\s+)?|for\s+less\s+than|<=?|≤)\s*{CURRENCY}\s*{NUMBER}\s*{CURRENCY}')),
    ('max', re.compile(rf'{CURRENCY}\s*\b{NUMBER}\s*{CURRENCY}\s*(?:or\s+less|or\s+below|or\s+under|and\s+under|'
                       rf'and\s+below|max(?:imum)?|tops|at\s+most)\b')),
    ('min', re.compile(rf'\b(?:over|above|more\s+than|greater\s+than|at\s+least|min(?:imum)?(?:\s+of)?|'
                       rf'starting\s+(?:at|from)|costlier\s+than|pricier\s+than|>=?|≥)\s*{CURRENCY}\s*{NUMBER}\s*{CURRENCY}')),
    ('min', re.compile(rf'{CURRENCY}\s*\b{NUMBER}\s*{CURRENCY}\s*(?:or\s+more|or\s+above|and\s+(?:above|up|over)|\+|plus)')),
    ('around', re.compile(rf'\b(?:around|about|approximately|approx\.?|roughly|close\s+to|near)\s*{CURRENCY}\s*{NUMBER}\s*{CURRENCY}')),
    ('max', re.compile(rf'\b(?:for|at|costing|priced\s+at)\s+(?:inr|rs\.?|₹)\s*{NUMBER}')),
    ('max', re.compile(rf'(?:inr|rs\.?)\s*{NUMBER}\b|\b{NUMBER}\s*(?:inr|rs\b|rupees?)')),
    ('max', re.compile(r'\b(\d+(?:\.\d+)?)\s*(k)\b')),
]
RATING_PATTERNS = [
    re.compile(r'\b(\d(?:\.\d)?)\s*(?:\+|plus)?\s*(?:stars?|star\s+rating)(?:\s+(?:and|or)\s+(?:above|up|more|higher))?'),
    re.compile(r'\brat(?:ed|ing|ings)\s+(?:of\s+)?(?:at\s+least|above|over|>=?|more\s+than|minimum|min)?\s*(\d(?:\.\d)?)'),
    re.compile(r'\b(?:at\s+least|above|over|minimum)\s+(\d(?:\.\d)?)\s*(?:stars?|rating)'),
]
REVIEWS_PATTERN = re.compile(r'\b(?:at\s+least|over|more\s+than|minimum|min)?\s*(\d+)\s*\+?\s*reviews?\b')
EACH = re.compile(r'\b(each|apiece|per\s+(?:item|piece)|both|all\s+(?:of\s+them|under|below|items)|everything)\b')
SPLIT = re.compile(r'\s*(?:,|;|/|\band\b|\bor\b|\bplus\b|\bas\s+well\s+as\b|\balso\b|\btogether\s+with\b)\s*')
PLAIN_WITH = re.compile(r'\bwith\s+(?:an?\s+|some\s+|the\s+|my\s+)?')


@dataclass
class Choice:
    text: str
    tokens: list = field(default_factory=list)
    concepts: list = field(default_factory=list)
    colors: set = field(default_factory=set)
    color_primary: set = field(default_factory=set)
    exclude_colors: set = field(default_factory=set)
    exclude_concepts: set = field(default_factory=set)
    exclude_terms: set = field(default_factory=set)
    patterns: set = field(default_factory=set)
    pattern_terms: list = field(default_factory=list)
    material_terms: list = field(default_factory=list)
    style_terms: list = field(default_factory=list)
    occasions: list = field(default_factory=list)
    content: list = field(default_factory=list)
    unknown: list = field(default_factory=list)
    audience: str = None
    min_price: float = None
    max_price: float = None
    complement: bool = False


@dataclass
class ParsedQuery:
    raw: str
    choices: list
    complements: list
    min_rating: float = None
    min_reviews: int = None
    prefer_cheap: bool = False
    prefer_expensive: bool = False
    prefer_rating: bool = False
    abstain: str = None


def _amount(num, k):
    value = float(num) * (1000 if k else 1)
    return value


def extract_prices(text):
    """Return (text without price phrases, [(kind, lo, hi, position)])."""
    found = []
    for kind, pattern in PRICE_PATTERNS:
        for m in pattern.finditer(text):
            if any(m.start() < e and s < m.end() for s, e, *_ in found):
                continue
            g = m.groups()
            # (number, k-suffix) pairs from whichever alternative matched
            pairs = [(g[i], g[i + 1]) for i in range(0, len(g) - 1, 2) if g[i] is not None]
            if not pairs or (kind == 'range' and len(pairs) < 2):
                continue
            if kind == 'range':
                lo, hi = sorted((_amount(*pairs[0]), _amount(*pairs[1])))
            else:
                v = _amount(*pairs[0])
                if v < 20 and not g[1]:
                    continue  # pack sizes, counts and sizes rather than prices
                lo, hi = {'max': (None, v), 'min': (v, None), 'around': (v * 0.8, v * 1.2)}[kind]
            found.append((m.start(), m.end(), lo, hi))
    found.sort()
    for s, e, *_ in reversed(found):
        text = text[:s] + ' ' * (e - s) + text[e:]
    return text, [(lo, hi, s) for s, e, lo, hi in found]


ENGLISH_PATH = __import__('pathlib').Path(__file__).resolve().parent / 'data/english_words.txt.gz'
ENGLISH = set(gzip.open(ENGLISH_PATH, 'rt').read().split()) if ENGLISH_PATH.exists() else set()


def is_english(word):
    """Real dictionary words (and simple inflections) are never 'corrected'."""
    if word in ENGLISH:
        return True
    for suffix, repl in (('s', ''), ('es', ''), ('ing', ''), ('ing', 'e'), ('ed', ''), ('ed', 'e'), ('ies', 'y')):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3 and word[:-len(suffix)] + repl in ENGLISH:
            return True
    return False


class Vocabulary:
    """Catalog token statistics used for spelling correction and abstention."""

    def __init__(self, doc_freq, desc_terms=None):
        self.doc_freq = doc_freq
        self.desc_terms = desc_terms if desc_terms is not None else set(doc_freq)
        lexicon_terms = sorted(KNOWN - STOP)
        frequent = sorted(t for t, n in doc_freq.items() if n >= 3 and len(t) >= 4 and not t.isdigit())
        self.lexicon_terms = lexicon_terms
        self.frequent = frequent

    def __contains__(self, token):
        return token in self.doc_freq or token in KNOWN

    @lru_cache(maxsize=8192)
    def correct(self, token):
        """Conservative typo correction, preferring shopping vocabulary."""
        df = self.doc_freq.get(token, 0)
        if (token in KNOWN or token.isdigit() or len(token) < 4 or df >= 50 or is_english(token)
                or token in L.OFF_TOPIC or token in L.FOREIGN_BRANDS or token in L.UNAVAILABLE):
            return token
        limit = 1 if len(token) < 8 else 2
        # Rare catalog spellings ("sweter") still defer to a much more common shopping word.
        sources = (self.lexicon_terms,) if df else (self.lexicon_terms, self.frequent if len(token) >= 6 else ())
        for choices in sources:
            best = process.extractOne(token, choices, scorer=Levenshtein.distance, score_cutoff=limit)
            if best and (best[0][0] == token[0] or best[1] <= 1) and fuzz.ratio(token, best[0]) >= 75:
                if not df or self.doc_freq.get(best[0], 0) >= 20 * df or best[0] in CONCEPT_TERMS:
                    return best[0]
        if token not in self.doc_freq and token.endswith('s') and stem(token) in self:
            return stem(token)
        return token


def _color_at(tokens, i):
    """Detect a color starting at token i; returns (catalog colors, primary, width)."""
    word = tokens[i]
    nxt = tokens[i + 1] if i + 1 < len(tokens) else ''
    if word in ('light', 'dark', 'pale', 'deep', 'bright') and nxt in COLOR_WORDS:
        tone = {'pale': 'light', 'deep': 'dark', 'bright': ''}[word] if word in ('pale', 'deep', 'bright') else word
        base = L.COLOR_PRIMARY.get(nxt, COLOR_WORDS[nxt][0])
        base = base.split()[-1]
        exact = f'{tone.title()} {base}'.strip()
        family = [c for c in COLOR_WORDS[nxt] if c == exact] or COLOR_WORDS[nxt]
        return set(family), {exact}, 2
    if word == 'offwhite':
        return {'Off White'}, {'Off White'}, 1
    if word in COLOR_WORDS and not (word == 'rose' and nxt == 'gold'):
        if word == 'navy' and nxt == 'blue':
            return {'Dark Blue'}, {'Dark Blue'}, 2
        primary = L.COLOR_PRIMARY.get(word, COLOR_WORDS[word][0])
        return set(COLOR_WORDS[word]), {primary}, 1
    if word == 'pastel':
        return {'Light Pink', 'Light Blue', 'Light Green', 'Light Purple', 'Light Yellow', 'Light Turquoise',
                'Light Orange', 'Light Beige'}, set(), 1
    if word in ('dark', 'light') and nxt in ('colour', 'color', 'colours', 'colors', 'shade', 'tone'):
        if word == 'dark':
            return {'Black', 'Dark Blue', 'Dark Grey', 'Dark Green', 'Dark Red', 'Dark Purple', 'Dark Beige',
                    'Dark Turquoise', 'Dark Orange', 'Dark Pink', 'Dark Yellow'}, set(), 2
        return {'Light Pink', 'Light Blue', 'Light Green', 'Light Purple', 'Light Yellow', 'Light Turquoise',
                'Light Orange', 'Light Beige', 'Light Grey', 'White', 'Off White'}, set(), 2
    return None


def parse_choice(text, vocab, complement=False):
    choice = Choice(text=re.sub(r'\s+', ' ', text).strip(), complement=complement)
    raw = [w.replace("'", '') for w in WORD.findall(text)]
    tokens = []
    for w in raw:
        s = stem(w)
        if vocab is not None and s not in KNOWN:
            s = stem(vocab.correct(s))
        tokens.append(s)
    choice.tokens = tokens
    joined = ' '.join(tokens)
    for phrase, name in CONCEPT_PHRASES:
        if phrase in joined and name not in choice.concepts:
            choice.concepts.append(name)
    i, negate_until = 0, -1
    while i < len(tokens):
        t = tokens[i]
        if t in NEGATION:
            negate_until = i + 3
            i += 1
            continue
        negated = i <= negate_until
        color = _color_at(tokens, i)
        if color:
            colors, primary, width = color
            if negated:
                choice.exclude_colors |= colors if not primary else primary | (colors if width == 1 else set())
            else:
                choice.colors |= colors
                choice.color_primary |= primary
            i += width
            continue
        if t in CONCEPT_TERMS:
            names = CONCEPT_TERMS[t]
            # "top" right after a garment noun is part of that noun ("bikini top", "tank top").
            if t == 'top' and choice.concepts and i > 0 and tokens[i - 1] in CONCEPT_TERMS:
                i += 1
                continue
            if negated:
                choice.exclude_concepts.update(names)
            else:
                for n in names:
                    if n not in choice.concepts:
                        choice.concepts.append(n)
            i += 1
            continue
        if t in PATTERN_WORDS:
            key = PATTERN_WORDS[t]
            terms = L.PATTERN_TEXT.get(key, {key})
            if negated:
                choice.exclude_terms |= terms
            else:
                choice.patterns |= set(L.PATTERNS.get(key) or [])
                choice.pattern_terms.append(sorted({stem(x) for x in terms}))
        elif t in MATERIAL_WORDS:
            key = MATERIAL_WORDS[t]
            terms = L.MATERIAL_TEXT.get(key, {key})
            if negated:
                choice.exclude_terms |= terms
            else:
                choice.material_terms.append(sorted({stem(x) for x in terms}))
        elif t in OCCASION_WORDS:
            choice.occasions.append(OCCASION_WORDS[t])
        elif t in L.AUDIENCE_WORDS or w_audience(t):
            choice.audience = w_audience(t)
        elif t in STYLE_WORDS:
            choice.style_terms.append(t)
        elif t not in STOP and not t.isdigit():
            if vocab is None or t in vocab:
                choice.content.append(t)
            else:
                choice.unknown.append(t)
        i += 1
    return choice


def w_audience(token):
    return L.AUDIENCE_WORDS.get(token) or L.AUDIENCE_WORDS.get(token + 's')


def _segments(text):
    parts = [p for p in SPLIT.split(text) if p and p.strip()]
    return parts


def split_complement(text):
    """Split primary text from an explicitly requested accompanying item."""
    m = L.COMPLEMENT_MARKERS.search(text)
    if m:
        before, after = text[:m.start()], text[m.end():]
        if any(CONCEPT_TERMS.get(stem(w)) for w in WORD.findall(after)):
            return before, after
        # "a bikini with sunglasses to go with it": the item before the marker is the complement.
        inner_primary, inner_comp = split_complement(before)
        if inner_comp:
            return inner_primary, inner_comp
        parts = _segments(before)
        if len(parts) > 1 and any(CONCEPT_TERMS.get(stem(w)) for w in WORD.findall(parts[-1])):
            return ' '.join(parts[:-1]), parts[-1]
        return before, ''
    for m in PLAIN_WITH.finditer(text):
        rest = text[m.end():]
        first = [stem(w) for w in WORD.findall(rest)[:3]]
        names = [n for w in first for n in CONCEPT_TERMS.get(w, [])]
        head = [stem(w) for w in WORD.findall(text[:m.start()])]
        head_concepts = [n for w in head for n in CONCEPT_TERMS.get(w, [])]
        if names and head_concepts and all(n in L.ACCESSORY_CONCEPTS for n in names) \
                and not set(names) & set(head_concepts) and not set(names) <= {'belt', 'tie', 'hat', 'hair'}:
            return text[:m.start()], rest
    return text, ''


def _group_choices(text, vocab, complement=False):
    """Split a phrase into choices; fragments without a garment merge into neighbours."""
    pieces = [parse_choice(p, vocab, complement) for p in _segments(text)]
    groups, pending = [], []
    for piece in pieces:
        if piece.concepts:
            if pending:
                piece = parse_choice(' '.join(p.text for p in pending) + ' ' + piece.text, vocab, complement)
                pending = []
            groups.append(piece)
        else:
            pending.append(piece)
    if pending:
        tail = ' '.join(p.text for p in pending)
        if groups:
            last = groups.pop()
            groups.append(parse_choice(last.text + ' ' + tail, vocab, complement))
        else:
            groups.append(parse_choice(tail, vocab, complement))
    # Keep original text spans for embedding queries.
    return [g for g in groups if g.tokens]


def parse(query, vocab=None):
    text = normalize(query)
    parsed = ParsedQuery(raw=query, choices=[], complements=[])
    for pattern in RATING_PATTERNS:
        m = pattern.search(text)
        if m:
            value = float(m.group(1))
            if 1 <= value <= 5:
                parsed.min_rating = value
                text = text[:m.start()] + ' ' + text[m.end():]
            break
    m = REVIEWS_PATTERN.search(text)
    if m and re.search(r'\b(?:at\s+least|over|more\s+than|minimum|min)\b|\+', m.group(0)):
        parsed.min_reviews = int(m.group(1))
        text = text[:m.start()] + ' ' + text[m.end():]
    if re.search(r'\b(highly|top|best|well|good)[\s-]+(rated|reviewed)\b|\bbest\s+reviews?\b|\bhigh\s+ratings?\b', text):
        parsed.prefer_rating = True
    if re.search(r'\b(cheap|cheapest|affordable|inexpensive|budget|low[\s-]cost|bargain|economical)\b', text):
        parsed.prefer_cheap = True
    if re.search(r'\b(expensive|premium|luxury|luxurious|high[\s-]end|designer|priciest)\b', text):
        parsed.prefer_expensive = True
    each = bool(EACH.search(text))
    text = re.sub(r'(\d),(\d{3})\b', r'\1\2', text)
    text, prices = extract_prices(text)
    primary_text, complement_text = split_complement(text)
    parsed.choices = _group_choices(primary_text, vocab)
    if complement_text.strip():
        parsed.complements = _group_choices(complement_text, vocab, complement=True)
        for c in parsed.complements:
            if not c.concepts:
                c.concepts = []
    _assign_prices(parsed, prices, text, primary_text, each)
    _assign_audience(parsed)
    parsed.abstain = _abstain_reason(parsed, vocab)
    return parsed


def _assign_prices(parsed, prices, text, primary_text, each):
    if not prices:
        return
    allc = parsed.choices + parsed.complements
    if not allc:
        return
    # Locate each choice's span in the normalized text to attach local budgets.
    spans, cursor = [], 0
    for c in allc:
        first = c.text.split()[0] if c.text.split() else ''
        pos = text.find(first, cursor) if first else cursor
        pos = cursor if pos < 0 else pos
        spans.append(pos)
        cursor = pos + 1
    def owner(position):
        idx = 0
        for i, s in enumerate(spans):
            if s <= position:
                idx = i
        return idx
    primary_count = len(parsed.choices)
    if each or len(prices) == 1:
        lo, hi, pos = prices[0]
        target = owner(pos)
        local_complement = target >= primary_count
        if len(prices) == 1 and not each and target < primary_count - 1:
            targets = [target]
        elif local_complement and not each:
            targets = [target]
        else:
            targets = list(range(len(allc)))
        for i in targets:
            _set_price(allc[i], lo, hi)
        return
    assigned = set()
    for lo, hi, pos in prices:
        i = owner(pos)
        _set_price(allc[i], lo, hi)
        assigned.add(i)
    # Accompanying items inherit the primary budget unless given their own (per-item budgets).
    for i in range(primary_count, len(allc)):
        if i not in assigned and parsed.choices:
            src = parsed.choices[-1]
            _set_price(allc[i], src.min_price, src.max_price)


def _set_price(choice, lo, hi):
    if lo is not None:
        choice.min_price = lo if choice.min_price is None else max(choice.min_price, lo)
    if hi is not None:
        choice.max_price = hi if choice.max_price is None else min(choice.max_price, hi)


def _assign_audience(parsed):
    found = {c.audience for c in parsed.choices + parsed.complements if c.audience}
    if len(found) == 1:
        audience = found.pop()
        for c in parsed.choices + parsed.complements:
            c.audience = audience


def _abstain_reason(parsed, vocab):
    choices = parsed.choices
    if not choices:
        return 'empty'
    tokens = {t for c in choices + parsed.complements for t in c.tokens}
    tokens |= {w for w in WORD.findall(normalize(parsed.raw))}  # unstemmed forms too
    catalog_has = (lambda t: t in vocab.doc_freq) if vocab is not None else (lambda t: True)
    described = (lambda t: t in vocab.desc_terms) if vocab is not None else (lambda t: True)
    for t in tokens:
        if t in L.FOREIGN_BRANDS and not described(t):
            return f'brand not in catalog: {t}'
        if t in L.UNAVAILABLE and not catalog_has(t):
            return f'product not in catalog: {t}'
    has_concept = any(c.concepts for c in choices)
    if not has_concept:
        if tokens & OFF_TOPIC:
            return 'off-topic request'
        signal = any(c.colors or c.patterns or c.pattern_terms or c.material_terms or c.occasions
                     or c.style_terms or c.audience for c in choices)
        content = [t for c in choices for t in c.content]
        unknown = [t for c in choices for t in c.unknown]
        if not signal and not content:
            return 'no shopping evidence'
        if unknown and not signal and len(unknown) >= max(1, len(content)):
            return 'unrecognized request'
    else:
        hard_off = tokens & (OFF_TOPIC - L.SOFT_OFF_TOPIC)
        if hard_off and not any(catalog_has(t) for t in hard_off):
            return 'off-topic request'
    return None
