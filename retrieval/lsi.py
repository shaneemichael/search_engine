import os
import pickle
import numpy as np

from storage import InvertedIndexReader
from .adaptive import LSI_INDEX_FILE, LSI_PARAMS_FILE


def build_lsi(index, dimensions=100):
    """
    Builds the Latent Semantic Indexing model of a loaded lexical index and
    saves it next to that index (`lsi.faiss` + `lsi_params.pkl`).

      1. Materializes the term-document matrix as a SciPy CSC sparse matrix,
         weighted with (1 + log tf) * idf.
      2. Runs truncated SVD (`scipy.sparse.linalg.svds`) keeping `dimensions`
         latent factors, so co-occurring terms land close together.
      3. Projects documents (V * S) into the latent space, L2-normalizes them and
         stores them in a `faiss.IndexFlatIP` (inner product == cosine).
      4. Saves term vectors (U * S^-1) so queries can be folded into the same space.
    """
    import faiss
    import scipy.sparse as sp
    from scipy.sparse.linalg import svds

    num_terms = len(index.term_id_map)
    num_docs = len(index.doc_id_map)

    rows, cols, data = [], [], []
    with InvertedIndexReader(index.index_name, index.postings_encoding, directory=index.output_dir) as reader:
        for term_id, (_, df, _, _) in reader.postings_dict.items():
            postings, tf_list = reader.get_postings_list(term_id)
            idf = np.log(num_docs / (df + 1))
            for doc_id, tf in zip(postings, tf_list):
                rows.append(term_id)
                cols.append(doc_id)
                data.append((1 + np.log(tf)) * idf)

    matrix = sp.csc_matrix((data, (rows, cols)), shape=(num_terms, num_docs))

    k = min(dimensions, num_terms - 1, num_docs - 1)
    if k <= 0:
        raise ValueError("Corpus too small for SVD")
    U, Sigma, VT = svds(matrix, k=k)

    term_vectors = U.astype(np.float32) * (1.0 / Sigma).astype(np.float32)
    doc_vectors = VT.T.astype(np.float32) * Sigma.astype(np.float32)
    norms = np.linalg.norm(doc_vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10

    faiss_index = faiss.IndexFlatIP(k)
    faiss_index.add(doc_vectors / norms)

    with open(os.path.join(index.output_dir, LSI_PARAMS_FILE), 'wb') as f:
        pickle.dump({'term_vectors': term_vectors}, f)
    faiss.write_index(faiss_index, os.path.join(index.output_dir, LSI_INDEX_FILE))
