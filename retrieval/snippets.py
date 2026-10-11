import re

from text import tokenize

_WORD = re.compile(r'\S+')
_PUNCT = re.compile(r'^(\W*)(.*?)(\W*)$', re.S)


def _is_hit(word, query_terms):
    return any(stem in query_terms for stem in tokenize(word))


def _hit_segments(word):
    """A matched word as segments, keeping surrounding punctuation outside the highlight."""
    pre, core, post = _PUNCT.match(word).groups()
    return [(t, hit) for t, hit in ((pre, False), (core or word, True), (post, False)) if t]


def read_document(doc_path):
    with open(doc_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


def document_title(text, max_len=110):
    """The opening sentence of a document, skipping bare numbering like '1972.'"""
    flat = re.sub(r'^\d+\.\s*', '', " ".join(text.split()))
    for sentence in re.split(r'(?<=\.)\s+', flat):
        if not re.fullmatch(r'[\d.\s]*', sentence):
            title = sentence.rstrip(' .')
            return title if len(title) <= max_len else title[:max_len].rsplit(' ', 1)[0] + '…'
    return flat[:max_len]


def highlight(text, query):
    """
    Splits `text` into segments [(text, is_hit), ...] where hits are words whose
    stem matches a query term, so 'tumors' is highlighted for the query 'tumor'.
    Whitespace is preserved.
    """
    query_terms = set(tokenize(query))
    segments, last = [], 0
    for m in _WORD.finditer(text):
        if query_terms and _is_hit(m.group(), query_terms):
            if m.start() > last:
                segments.append((text[last:m.start()], False))
            segments.extend(_hit_segments(m.group()))
            last = m.end()
    if last < len(text):
        segments.append((text[last:], False))
    return segments


def snippet(query, text, window_size=30):
    """
    The `window_size`-word window of `text` containing the most query-term hits,
    as highlight segments. Ellipses mark truncation on either side.
    """
    query_terms = set(tokenize(query))
    words = text.split()
    if not words:
        return []

    hits = [_is_hit(w, query_terms) for w in words]
    best_start, best_score = 0, -1
    score = sum(hits[:window_size])
    for start in range(max(1, len(words) - window_size + 1)):
        if start > 0:
            score += hits[start + window_size - 1] - hits[start - 1]
        if score > best_score:
            best_start, best_score = start, score

    end = best_start + window_size
    segments = [("… ", False)] if best_start > 0 else []
    for i, word in enumerate(words[best_start:end]):
        if i > 0:
            segments.append((" ", False))
        segments.extend(_hit_segments(word) if hits[best_start + i] else [(word, False)])
    if end < len(words):
        segments.append((" …", False))
    return segments
