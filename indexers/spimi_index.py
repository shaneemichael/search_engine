from .bsbi_index import BSBIIndex
from dictionary import TrieIdMap
from text import tokenize

class SPIMIIndex(BSBIIndex):
    """
    Single-Pass In-Memory Indexing (SPIMI) implementation scaling on BSBIIndex.
    Uses a Trie dictionary to share common prefixes between terms in memory.
    Constructs each block without materializing a list of (term, doc) pairs.
    """
    def __init__(self, data_dir, output_dir, postings_encoding, index_name="spimi_index"):
        super().__init__(data_dir, output_dir, postings_encoding, index_name)
        # Override the standard IdMap with the Trie-based dictionary structure
        self.term_id_map = TrieIdMap()
        self.doc_id_map = TrieIdMap()

    def invert_block(self, block_dir_relative, index):
        """
        Parses exactly one document block directly into `term_dict` and `term_tf` in memory,
        then writes it sequentially to `index` (an InvertedIndexWriter).

        Single-Pass In-Memory Indexing:
          BSBI materializes every (term_id, doc_id) pair of the block into a list before
          inverting it. SPIMI skips that list:
          1. Reads the block token-by-token.
          2. Adds each doc_id straight into a postings `set()` keyed by `term_id`.
          3. When the block finishes, sorts only the vocabulary of the block
             (O(V log V) on the unique terms, not on the total number of tokens).
          4. Flushes the block's postings to disk.

        Peak memory is proportional to the block's postings rather than its token count.
        """
        term_dict = {}
        term_tf = {}

        for docname in self.block_documents(block_dir_relative):
            with open(docname, "r", encoding="utf8", errors="surrogateescape") as f:
                doc_id = self.doc_id_map[docname]
                for token in tokenize(f.read()):
                    term_id = self.term_id_map[token]
                    if term_id not in term_dict:
                        term_dict[term_id] = set()
                        term_tf[term_id] = {}
                    term_dict[term_id].add(doc_id)
                    term_tf[term_id][doc_id] = term_tf[term_id].get(doc_id, 0) + 1

        for term_id in sorted(term_dict.keys()):
            sorted_doc_id = sorted(term_dict[term_id])
            assoc_tf = [term_tf[term_id][doc_id] for doc_id in sorted_doc_id]
            index.append(term_id, sorted_doc_id, assoc_tf)
