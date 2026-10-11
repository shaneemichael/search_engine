import os
import pickle
import numpy as np

from text import tokenize

LSI_INDEX_FILE = 'lsi.faiss'
LSI_PARAMS_FILE = 'lsi_params.pkl'


class AdaptiveRetriever:
    """
    Hybrid retrieval: fuses BM25-WAND lexical scores with LSI semantic scores
    (FAISS inner product over SVD document vectors) after min-max normalization.
    Single-term queries lean on the lexical side, where LSI adds mostly noise.
    """
    def __init__(self, lexical_index):
        import faiss

        self.lexical_index = lexical_index
        output_dir = lexical_index.output_dir
        try:
            self.faiss_idx = faiss.read_index(os.path.join(output_dir, LSI_INDEX_FILE))
            with open(os.path.join(output_dir, LSI_PARAMS_FILE), 'rb') as f:
                self.term_vectors = pickle.load(f)['term_vectors']
        except (OSError, RuntimeError) as e:
            raise RuntimeError(f"No LSI model in {output_dir}. Build it with `python build.py`. ({e})") from e

        self.num_docs = len(self.lexical_index.doc_id_map)

    def query_to_lsi_vector(self, query):
        q_vec = np.zeros(self.term_vectors.shape[1], dtype=np.float32)
        valid_terms = 0

        for token in set(tokenize(query)):
            if token in self.lexical_index.term_id_map.str_to_id:
                q_vec += self.term_vectors[self.lexical_index.term_id_map[token]]
                valid_terms += 1

        if valid_terms > 0:
            q_vec /= np.linalg.norm(q_vec) + 1e-10

        return np.expand_dims(q_vec, 0)

    def retrieve_adaptive(self, query, k=10, faiss_weight=0.6):
        wand_results = self.lexical_index.retrieve_bm25_wand(query, k=100)

        q_vec = self.query_to_lsi_vector(query)
        D, I = self.faiss_idx.search(q_vec, min(self.num_docs, 100))

        lex_scores = {doc: score for score, doc in wand_results}
        sem_scores = {}
        for score, doc_id in zip(D[0], I[0]):
            if 0 <= doc_id < self.num_docs:
                sem_scores[self.lexical_index.doc_id_map[int(doc_id)]] = float(score)

        min_lex = min(lex_scores.values(), default=0)
        lex_range = max(max(lex_scores.values(), default=0) - min_lex, 1e-5)
        min_sem = min(sem_scores.values(), default=0)
        sem_range = max(max(sem_scores.values(), default=0) - min_sem, 1e-5)

        if len(tokenize(query)) <= 1:
            faiss_weight = 0.2

        combined = []
        for doc in set(lex_scores) | set(sem_scores):
            norm_lex = (lex_scores.get(doc, min_lex) - min_lex) / lex_range if lex_scores else 0
            norm_sem = (sem_scores.get(doc, min_sem) - min_sem) / sem_range if sem_scores else 0
            combined.append(((1 - faiss_weight) * norm_lex + faiss_weight * norm_sem, doc))

        combined.sort(key=lambda x: x[0], reverse=True)
        return combined[:k]
