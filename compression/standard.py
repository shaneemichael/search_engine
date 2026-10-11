import array

class StandardPostings:
    """ 
    Class with static methods, to change the representation of the postings list
    which originally is a List of integers, into a sequence of bytes.
    We use the array library in Python.

    ASSUMPTION: the postings_list for a term FITS in memory!

    Please study:
        https://docs.python.org/3/library/array.html
    """

    @staticmethod
    def encode(postings_list):
        """
        Encode postings_list into a stream of bytes

        Parameters
        ----------
        postings_list: List[int]
            List of docIDs (postings)

        Returns
        -------
        bytes
            bytearray representing the sequence of integers in postings_list
        """
        # 'I' (unsigned int) is 4 bytes on every mainstream platform, unlike
        # 'L' (unsigned long), which is 8 bytes on Linux and 4 on Windows.
        return array.array('I', postings_list).tobytes()

    @staticmethod
    def decode(encoded_postings_list):
        """
        Decodes postings_list from a stream of bytes

        Parameters
        ----------
        encoded_postings_list: bytes
            bytearray representing the encoded postings list as output
            from the encode static method above.

        Returns
        -------
        List[int]
            list of docIDs that is the result of decoding encoded_postings_list
        """
        decoded_postings_list = array.array('I')
        decoded_postings_list.frombytes(encoded_postings_list)
        return decoded_postings_list.tolist()

    @staticmethod
    def encode_tf(tf_list):
        """
        Encode list of term frequencies into a stream of bytes

        Parameters
        ----------
        tf_list: List[int]
            List of term frequencies

        Returns
        -------
        bytes
            bytearray representing the raw TF value of term occurrences in each
            document in the postings list
        """
        return StandardPostings.encode(tf_list)

    @staticmethod
    def decode_tf(encoded_tf_list):
        """
        Decodes list of term frequencies from a stream of bytes

        Parameters
        ----------
        encoded_tf_list: bytes
            bytearray representing the encoded term frequencies list as output
            from the encode_tf static method above.

        Returns
        -------
        List[int]
            List of term frequencies that is the result of decoding encoded_tf_list
        """
        return StandardPostings.decode(encoded_tf_list)
