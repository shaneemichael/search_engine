# Scalpel: a search engine from scratch

An information retrieval engine over the MEDLINE test collection (1,033 medical abstracts, 30 judged queries), built without IR or NLP libraries: tokenizer and Porter stemmer, BSBI and SPIMI indexing, three term dictionaries, three postings codecs, TF-IDF / BM25 / WAND ranking, and an LSI + FAISS semantic hybrid. It comes with a CLI, an evaluation harness and a web app.

## Quick start

```bash
pip install -r requirements.txt
python build.py --all        # builds all 9 index configurations (~30 s)
python -m web                # http://127.0.0.1:8000
```

The web app has four views:

| View | What it shows |
| --- | --- |
| **Search** | Ranked results with highlighted snippets, the query's stemming pipeline, WAND pruning stats, and relevance badges when the query is one of the 30 benchmark queries. Click a result to read the document. |
| **Compare** | TF-IDF, BM25, WAND and Adaptive side by side for one query, with lines tracing each document's rank across rankers. |
| **Index Lab** | Collection-wide postings size per codec, a postings inspector that shows the bit layout of VByte and Elias-Gamma codes for any term, and the 3×3 build matrix with live rebuilds. |
| **Evaluation** | RBP / DCG / NDCG / MAP for five retrieval setups, plus a per-query breakdown of where the hybrid beats BM25. |

## Deploying to Vercel

`pyproject.toml` points Vercel at `web.app:app`. The deployment file system is read-only, so on Vercel the indexes are built into `/tmp/index` on demand: the first request to a fresh instance builds the default index (~4 s), and other configurations are built the first time they are used. Set `TBI_INDEX_DIR` to choose another index location anywhere.

## Components

- **Text processing** (`text/`): lowercase → alphabetic tokens → stopword removal → Porter stemming.
- **Indexing** (`indexers/`): BSBI inverts each block from (term, doc) pairs; SPIMI builds each block's postings directly in a hash map. Blocks are merged with an external multi-way merge.
- **Dictionaries** (`dictionary/`): hash map `IdMap`, character `TrieIdMap`, compressed `PatriciaTreeIdMap`.
- **Postings codecs** (`compression/`): uncompressed 4-byte integers, gap + Variable-Byte, gap + Elias-Gamma (bit-packed).
- **Ranking**: TF-IDF and BM25 (`k1=1.2`, `b=0.75`) term-at-a-time; BM25 with WAND document-at-a-time pruning, using per-term score upper bounds precomputed during the merge.
- **Semantic hybrid** (`retrieval/`): truncated SVD (k=100) over the weighted term-document matrix, document vectors in a FAISS inner-product index, fused with BM25-WAND after min-max normalization.

## Index configurations

Each (indexer, dictionary, codec) combination is built into its own directory, `index/<indexer>-<dictionary>-<codec>/`, so configurations never overwrite each other:

| Indexer | Dictionary | Codecs |
| --- | --- | --- |
| `bsbi` | `standard` | `standard`, `vbe`, `elias` |
| `spimi` | `trie` | `standard`, `vbe`, `elias` |
| `spimi` | `patricia` | `standard`, `vbe`, `elias` |

```bash
python build.py --index spimi --dictionary patricia --compression elias   # one configuration (the default)
python build.py --all --no-lsi                                            # all, skipping the semantic model
```

## CLI search

```bash
python search.py "tumor treatment" --metric wand --snippets
python search.py "viral infection" --index bsbi --dictionary standard --compression vbe --metric adaptive
python search.py                     # three sample queries, every method
```

Options: `--index`, `--dictionary`, `--compression` select the configuration (built on first use if missing); `--metric` is `tfidf`, `bm25`, `wand`, `adaptive` or `all`; `-k` sets the number of results; `--snippets` prints highlighted context.

## Evaluation

```bash
python evaluation.py
```

30 queries, ranked to depth 1000, scored against `qrels.txt`:

```text
Retrieval Architecture         | Time (s) | RBP     | DCG     | NDCG    | AP
---------------------------------------------------------------------------------
TF-IDF (BSBI)                  | 0.130    | 0.6467  | 5.7871  | 0.8211  | 0.5637
BM25 (BSBI)                    | 0.133    | 0.6722  | 5.8999  | 0.8307  | 0.5849
BM25-WAND (BSBI)               | 0.193    | 0.6903  | 5.9715  | 0.8372  | 0.5945
BM25-WAND (SPIMI + Trie)       | 0.290    | 0.6903  | 5.9715  | 0.8372  | 0.5945
Adaptive (BM25 + LSI)          | 0.643    | 0.7722  | 6.5673  | 0.8930  | 0.7058
```

The hybrid improves MAP by 20.7% over BM25 and is better on 25 of the 30 queries.

## Index sizes

Postings file for the whole collection:

| Codec | Size | vs. uncompressed |
| --- | --- | --- |
| Uncompressed | 478.5 KiB | — |
| Variable-Byte | 131.1 KiB | 3.65× smaller |
| Elias-Gamma | 168.0 KiB | 2.85× smaller |

Elias-Gamma is smaller for frequent terms with small gaps (`cancer`: 99 B vs. 159 B for VByte), yet VByte wins overall. Half the vocabulary (4,209 of 8,543 terms) occurs in a single document, and every Elias-Gamma list (doc IDs and TFs) starts with a 4-byte length header: those rare terms cost 49.7 KB in Elias-Gamma against 12.3 KB in VByte, which accounts for nearly the whole difference.

## Project layout

```text
build.py              build one or all index configurations
search.py             CLI search
evaluation.py         benchmark harness (RBP, DCG, NDCG, AP)
engine.py             index configurations, build(), SearchEngine facade
text/                 tokenizer and Porter stemmer
indexers/             BSBIIndex, SPIMIIndex, SPIMIPatriciaIndex
dictionary/           IdMap, TrieIdMap, PatriciaTreeIdMap
compression/          StandardPostings, VBEPostings, EliasGammaPostings
storage/              InvertedIndexReader / InvertedIndexWriter
retrieval/            AdaptiveRetriever, LSI builder, snippets
metrics/              rbp, dcg, ndcg, ap
web/                  FastAPI app (python -m web) and static frontend
collection/           the 1,033 documents, in 11 blocks
queries.txt, qrels.txt
```
