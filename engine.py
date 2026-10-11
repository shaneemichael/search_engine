"""
Index configurations and the search engine facade shared by the CLI, the
evaluation script and the web app.

Every (indexer, dictionary, compression) combination lives in its own
directory under `index/`, so building one never clobbers another.
"""
import json
import os
import re
import time
from dataclasses import dataclass

from compression import StandardPostings, VBEPostings, EliasGammaPostings
from indexers import BSBIIndex, SPIMIIndex, SPIMIPatriciaIndex

DATA_DIR = 'collection'
INDEX_ROOT = 'index'
INDEX_NAME = 'main_index'
META_FILE = 'meta.json'

COMPRESSIONS = {
    'standard': StandardPostings,
    'vbe': VBEPostings,
    'elias': EliasGammaPostings,
}

# (indexer, dictionary) -> index class. BSBI uses the hash-map IdMap;
# SPIMI comes with either a character Trie or a Patricia (radix) tree.
INDEX_CLASSES = {
    ('bsbi', 'standard'): BSBIIndex,
    ('spimi', 'trie'): SPIMIIndex,
    ('spimi', 'patricia'): SPIMIPatriciaIndex,
}

INDEXER_LABELS = {'bsbi': 'BSBI', 'spimi': 'SPIMI'}
DICTIONARY_LABELS = {'standard': 'Hash map', 'trie': 'Trie', 'patricia': 'Patricia tree'}
COMPRESSION_LABELS = {'standard': 'Uncompressed', 'vbe': 'Variable-Byte', 'elias': 'Elias-Gamma'}

METHODS = {
    'tfidf': 'TF-IDF',
    'bm25': 'BM25',
    'wand': 'BM25 + WAND',
    'adaptive': 'Adaptive (BM25 + LSI)',
}


@dataclass(frozen=True)
class IndexConfig:
    indexer: str = 'spimi'
    dictionary: str = 'patricia'
    compression: str = 'elias'

    def __post_init__(self):
        if (self.indexer, self.dictionary) not in INDEX_CLASSES:
            valid = ", ".join(f"{i}+{d}" for i, d in INDEX_CLASSES)
            raise ValueError(f"Unsupported indexer/dictionary '{self.indexer}+{self.dictionary}'. Use one of: {valid}")
        if self.compression not in COMPRESSIONS:
            raise ValueError(f"Unknown compression '{self.compression}'. Use one of: {', '.join(COMPRESSIONS)}")

    @classmethod
    def from_key(cls, key):
        return cls(*key.split('-'))

    @property
    def key(self):
        return f"{self.indexer}-{self.dictionary}-{self.compression}"

    @property
    def label(self):
        return " / ".join([INDEXER_LABELS[self.indexer],
                           DICTIONARY_LABELS[self.dictionary],
                           COMPRESSION_LABELS[self.compression]])

    @property
    def directory(self):
        return os.path.join(INDEX_ROOT, self.key)

    def new_index(self):
        cls = INDEX_CLASSES[(self.indexer, self.dictionary)]
        return cls(DATA_DIR, self.directory, COMPRESSIONS[self.compression], index_name=INDEX_NAME)

    def is_built(self):
        return os.path.exists(os.path.join(self.directory, META_FILE))

    def meta(self):
        with open(os.path.join(self.directory, META_FILE)) as f:
            return json.load(f)

    def file_sizes(self):
        """Bytes on disk per artifact: postings, postings metadata, dictionaries, LSI model."""
        def size(name):
            path = os.path.join(self.directory, name)
            return os.path.getsize(path) if os.path.exists(path) else 0
        return {
            'postings': size(f'{INDEX_NAME}.index'),
            'postings_meta': size(f'{INDEX_NAME}.dict'),
            'terms': size('terms.dict'),
            'docs': size('docs.dict'),
            'lsi': size('lsi.faiss') + size('lsi_params.pkl'),
        }


DEFAULT_CONFIG = IndexConfig()
ALL_CONFIGS = [IndexConfig(i, d, c) for (i, d) in INDEX_CLASSES for c in COMPRESSIONS]


def build(config, with_lsi=True):
    """Builds the inverted index (and optionally the LSI model) for `config`, timing each stage."""
    index = config.new_index()
    start = time.perf_counter()
    index.index()
    index_seconds = time.perf_counter() - start

    meta = {
        'config': config.key,
        'index_seconds': round(index_seconds, 3),
        'terms': len(index.term_id_map),
        'docs': len(index.doc_id_map),
        'built_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    if with_lsi:
        from retrieval import build_lsi
        start = time.perf_counter()
        build_lsi(index)
        meta['lsi_seconds'] = round(time.perf_counter() - start, 3)

    with open(os.path.join(config.directory, META_FILE), 'w') as f:
        json.dump(meta, f, indent=2)
    return meta


def doc_number(doc_path):
    """'collection/6/507.txt' -> 507, the id used by qrels.txt."""
    m = re.search(r'(\d+)\.txt$', doc_path)
    return int(m.group(1)) if m else None


class SearchEngine:
    """A loaded index plus its retrieval methods, addressed by method key (see METHODS)."""

    def __init__(self, config=DEFAULT_CONFIG, build_if_missing=True):
        self.config = config
        if not config.is_built():
            if not build_if_missing:
                raise FileNotFoundError(f"Index {config.key} is not built. Run `python build.py`.")
            build(config)
        self.index = config.new_index()
        self.index.load()
        self._adaptive = None

    @property
    def adaptive(self):
        if self._adaptive is None:
            from retrieval import AdaptiveRetriever
            self._adaptive = AdaptiveRetriever(self.index)
        return self._adaptive

    def search(self, method, query, k=10):
        """Returns [(score, doc_path), ...] best first."""
        if method == 'tfidf':
            return self.index.retrieve_tfidf(query, k=k)
        if method == 'bm25':
            return self.index.retrieve_bm25(query, k=k)
        if method == 'wand':
            return self.index.retrieve_bm25_wand(query, k=k)
        if method == 'adaptive':
            return self.adaptive.retrieve_adaptive(query, k=k)
        raise ValueError(f"Unknown method '{method}'. Use one of: {', '.join(METHODS)}")
