import time

from engine import IndexConfig, SearchEngine, doc_number
from metrics import rbp, dcg, ndcg, ap

METRICS = {'rbp': rbp, 'dcg': dcg, 'ndcg': ndcg, 'ap': ap}

# (label, index configuration, method) evaluated by default.
RUNS = [
    ("TF-IDF (BSBI)", IndexConfig('bsbi', 'standard', 'vbe'), 'tfidf'),
    ("BM25 (BSBI)", IndexConfig('bsbi', 'standard', 'vbe'), 'bm25'),
    ("BM25-WAND (BSBI)", IndexConfig('bsbi', 'standard', 'vbe'), 'wand'),
    ("BM25-WAND (SPIMI + Trie)", IndexConfig('spimi', 'trie', 'elias'), 'wand'),
    ("Adaptive (BM25 + LSI)", IndexConfig('spimi', 'patricia', 'elias'), 'adaptive'),
]


def load_qrels(qrel_file="qrels.txt"):
    """qrels[query_id] = set of relevant document numbers."""
    qrels = {}
    with open(qrel_file) as file:
        for line in file:
            qid, did = line.split()
            qrels.setdefault(qid, set()).add(int(did))
    return qrels


def load_queries(query_file="queries.txt"):
    """[(query_id, query_text), ...] in file order."""
    with open(query_file) as file:
        return [tuple(line.strip().split(maxsplit=1)) for line in file if line.strip()]


def evaluate(engine, method, queries, qrels, k=1000):
    """
    Runs every query through `engine` with `method` and scores the ranking.
    Returns {'seconds': float, 'mean': {metric: value}, 'per_query': {qid: {metric: value}}}.
    """
    per_query = {}
    start = time.perf_counter()
    for qid, query in queries:
        relevant = qrels.get(qid, set())
        ranking = [1 if doc_number(doc) in relevant else 0 for _, doc in engine.search(method, query, k=k)]
        per_query[qid] = {name: fn(ranking) for name, fn in METRICS.items()}
    seconds = time.perf_counter() - start
    mean = {name: sum(q[name] for q in per_query.values()) / len(per_query) for name in METRICS}
    return {'seconds': seconds, 'mean': mean, 'per_query': per_query}


def main():
    qrels = load_qrels()
    queries = load_queries()
    engines = {}

    header = f"{'Retrieval Architecture':<30} | {'Time (s)':<8} | {'RBP':<7} | {'DCG':<7} | {'NDCG':<7} | {'AP':<7}"
    print(header)
    print("-" * len(header))
    for label, config, method in RUNS:
        if config not in engines:
            engines[config] = SearchEngine(config)
        result = evaluate(engines[config], method, queries, qrels)
        m = result['mean']
        print(f"{label:<30} | {result['seconds']:<8.3f} | {m['rbp']:<7.4f} | {m['dcg']:<7.4f} | "
              f"{m['ndcg']:<7.4f} | {m['ap']:<7.4f}")


if __name__ == '__main__':
    main()
