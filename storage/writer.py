import os
import pickle
from .base import InvertedIndex

class InvertedIndexWriter(InvertedIndex):
    """
    Class that implements how to efficiently write an
    Inverted Index stored in a file.
    """
    def __enter__(self):
        self.index_file = open(self.index_file_path, 'wb+')
        return self

    def append(self, term, postings_list, tf_list, max_score=None):
        """
        Appends a term, postings_list, and the associated TF list 
        to the end of the index file.
        """
        self.terms.append(term) # update self.terms

        # update self.doc_length
        for i in range(len(postings_list)):
            doc_id, freq = postings_list[i], tf_list[i]
            if doc_id not in self.doc_length:
                self.doc_length[doc_id] = 0
            self.doc_length[doc_id] += freq

        # update max_score_dict for WAND
        if max_score is not None:
            self.max_score_dict[term] = max_score

        self.index_file.seek(0, os.SEEK_END)
        curr_position_in_byte = self.index_file.tell()
        compressed_postings = self.postings_encoding.encode(postings_list)
        compressed_tf_list = self.postings_encoding.encode_tf(tf_list)
        self.index_file.write(compressed_postings)
        self.index_file.write(compressed_tf_list)
        self.postings_dict[term] = (curr_position_in_byte, len(postings_list), \
                                    len(compressed_postings), len(compressed_tf_list))

    def __exit__(self, exception_type, exception_value, traceback):
        """Closes the index file and saves the metadata (postings dict, terms, doc lengths, WAND bounds)."""
        self.index_file.close()
        with open(self.metadata_file_path, 'wb') as f:
            pickle.dump([self.postings_dict, self.terms, self.doc_length, self.max_score_dict], f)
