import os
import re
import threading
import time
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from compression import EliasGammaPostings, StandardPostings, VBEPostings
from engine import (ALL_CONFIGS, COMPRESSION_LABELS, DEFAULT_CONFIG, DICTIONARY_LABELS, INDEXER_LABELS,
                    METHODS, IndexConfig, SearchEngine, build, doc_number)
from evaluation import RUNS, evaluate, load_qrels, load_queries
from retrieval import document_title, highlight, read_document, snippet
from storage import InvertedIndexReader
from text import tokenize

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')

app = FastAPI(title="Scalpel search engine")


@app.middleware('http')
async def no_stale_assets(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache'
    return response

QRELS = load_qrels()
QUERIES = load_queries()
QUERY_IDS = {" ".join(text.lower().split()): qid for qid, text in QUERIES}

_engines = {}
_engines_lock = threading.Lock()


def get_engine(config_key):
    try:
        config = IndexConfig.from_key(config_key)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e))
    with _engines_lock:
        if config not in _engines:
            engine = SearchEngine(config)
            engine.adaptive  # load the LSI model now, not on the first adaptive query
            _engines[config] = engine
        return _engines[config]


@lru_cache(maxsize=None)
def document(path):
    text = read_document(path)
    return text, document_title(text)


def benchmark_id(query):
    """The qid when `query` is one of the 30 benchmark queries, so results can be judged against qrels."""
    return QUERY_IDS.get(" ".join(query.lower().split()))


def analyze(query):
    """Each word of the query with the stem it indexes as, or None when it is dropped (stopword etc.)."""
    words = re.findall(r'[a-z]+', query.lower())
    return [{'word': w, 'stem': (tokenize(w) or [None])[0]} for w in words]


def run_method(engine, method, query, k):
    start = time.perf_counter()
    stats = None
    if method == 'wand':
        hits, stats = engine.index.retrieve_bm25_wand_with_stats(query, k=k)
    else:
        hits = engine.search(method, query, k=k)
    elapsed_ms = (time.perf_counter() - start) * 1000

    qid = benchmark_id(query)
    relevant = QRELS.get(qid, set())
    results = []
    for rank, (score, path) in enumerate(hits, start=1):
        text, title = document(path)
        results.append({
            'rank': rank,
            'path': path,
            'number': doc_number(path),
            'title': title,
            'score': float(score),
            'snippet': snippet(query, text),
            'relevant': (doc_number(path) in relevant) if qid else None,
        })
    return {
        'method': method,
        'label': METHODS[method],
        'elapsed_ms': elapsed_ms,
        'stats': stats,
        'results': results,
    }


def config_info(config):
    info = {
        'key': config.key,
        'indexer': config.indexer,
        'dictionary': config.dictionary,
        'compression': config.compression,
        'labels': [INDEXER_LABELS[config.indexer], DICTIONARY_LABELS[config.dictionary],
                   COMPRESSION_LABELS[config.compression]],
        'built': config.is_built(),
    }
    if info['built']:
        info['meta'] = config.meta()
        info['sizes'] = config.file_sizes()
    return info


@app.get('/api/overview')
def overview():
    engine = get_engine(DEFAULT_CONFIG.key)
    return {
        'documents': len(engine.index.doc_id_map),
        'terms': len(engine.index.term_id_map),
        'configs': len(ALL_CONFIGS),
        'default_config': DEFAULT_CONFIG.key,
        'methods': METHODS,
        'queries': [{'id': qid, 'text': text, 'relevant': len(QRELS.get(qid, ()))} for qid, text in QUERIES],
    }


@app.get('/api/search')
def search(q: str, method: str = 'adaptive', config: str = DEFAULT_CONFIG.key, k: int = 10):
    if method not in METHODS:
        raise HTTPException(400, f"Unknown method '{method}'")
    engine = get_engine(config)
    result = run_method(engine, method, q, max(1, min(k, 50)))
    qid = benchmark_id(q)
    result.update({
        'query': q,
        'analysis': analyze(q),
        'benchmark': {'id': qid, 'relevant_total': len(QRELS.get(qid, ()))} if qid else None,
        'config': config_info(engine.config),
    })
    return result


@app.get('/api/compare')
def compare(q: str, config: str = DEFAULT_CONFIG.key, k: int = 10):
    engine = get_engine(config)
    qid = benchmark_id(q)
    return {
        'query': q,
        'analysis': analyze(q),
        'benchmark': {'id': qid, 'relevant_total': len(QRELS.get(qid, ()))} if qid else None,
        'runs': [run_method(engine, method, q, max(1, min(k, 20))) for method in METHODS],
    }


@app.get('/api/document')
def get_document(path: str, q: str = ''):
    engine = get_engine(DEFAULT_CONFIG.key)
    if path not in engine.index.doc_id_map.str_to_id:
        raise HTTPException(404, "Unknown document")
    text, title = document(path)
    qid = benchmark_id(q) if q else None
    return {
        'path': path,
        'number': doc_number(path),
        'title': title,
        'words': len(text.split()),
        'segments': highlight(text, q),
        'relevant': (doc_number(path) in QRELS.get(qid, set())) if qid else None,
    }


@app.get('/api/configs')
def configs():
    return [config_info(c) for c in ALL_CONFIGS]


_build_lock = threading.Lock()


@app.post('/api/configs/{key}/build')
def rebuild(key: str):
    try:
        config = IndexConfig.from_key(key)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e))
    with _build_lock:
        with _engines_lock:
            _engines.pop(config, None)
        build(config)
    return config_info(config)


CODECS = {'standard': StandardPostings, 'vbe': VBEPostings, 'elias': EliasGammaPostings}


def _bits(data):
    return " ".join(f"{byte:08b}" for byte in data)


@app.get('/api/postings')
def postings(term: str, config: str = DEFAULT_CONFIG.key, sample: int = 8):
    """A term's postings list and how each codec lays it out on disk."""
    engine = get_engine(config)
    stems = tokenize(term)
    if not stems:
        raise HTTPException(404, f"'{term}' is a stopword or has no indexable characters")
    stem = stems[0]
    if stem not in engine.index.term_id_map.str_to_id:
        raise HTTPException(404, f"'{term}' (stem '{stem}') does not occur in the collection")
    term_id = engine.index.term_id_map[stem]

    with InvertedIndexReader(engine.index.index_name, engine.index.postings_encoding,
                             directory=engine.index.output_dir) as reader:
        doc_ids, tfs = reader.get_postings_list(term_id)
        upper_bound = reader.max_score_dict.get(term_id)

    gaps = [doc_ids[0]] + [b - a for a, b in zip(doc_ids, doc_ids[1:])]
    head = gaps[:sample]
    codecs = {
        'standard': {
            'bytes': len(StandardPostings.encode(doc_ids)) + len(StandardPostings.encode_tf(tfs)),
            'postings_bytes': len(StandardPostings.encode(doc_ids)),
            'codes': [_bits(StandardPostings.encode([d])) for d in doc_ids[:sample]],
        },
        'vbe': {
            'bytes': len(VBEPostings.encode(doc_ids)) + len(VBEPostings.encode_tf(tfs)),
            'postings_bytes': len(VBEPostings.encode(doc_ids)),
            'codes': [_bits(VBEPostings.vb_encode_number(g)) for g in head],
        },
        'elias': {
            'bytes': len(EliasGammaPostings.encode(doc_ids)) + len(EliasGammaPostings.encode_tf(tfs)),
            'postings_bytes': len(EliasGammaPostings.encode(doc_ids)),
            'codes': ["".join(map(str, EliasGammaPostings._encode_number(g))) for g in head],
        },
    }
    return {
        'term': term,
        'stem': stem,
        'term_id': term_id,
        'df': len(doc_ids),
        'cf': sum(tfs),
        'wand_upper_bound': upper_bound,
        'doc_ids': doc_ids[:sample],
        'tfs': tfs[:sample],
        'gaps': head,
        'codecs': codecs,
    }


_evaluation = None
_evaluation_lock = threading.Lock()


@app.get('/api/evaluation')
def evaluation():
    global _evaluation
    with _evaluation_lock:
        if _evaluation is None:
            runs = []
            for label, config, method in RUNS:
                result = evaluate(get_engine(config.key), method, QUERIES, QRELS)
                runs.append({'label': label, 'config': config.key, 'method': method, **result})
            _evaluation = {
                'runs': runs,
                'queries': [{'id': qid, 'text': text, 'relevant': len(QRELS.get(qid, ()))} for qid, text in QUERIES],
            }
    return _evaluation


@app.get('/')
def index_page():
    return FileResponse(os.path.join(STATIC_DIR, 'index.html'))


app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
