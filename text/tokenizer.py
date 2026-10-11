import re

# ---------------------------------------------------------------------------
# Minimal English stopword list (no external libraries)
# ---------------------------------------------------------------------------
STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'was', 'are', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'shall', 'can', 'this', 'that',
    'these', 'those', 'it', 'its', 'as', 'if', 'not', 'no', 'nor',
    'so', 'yet', 'both', 'either', 'neither', 'each', 'few', 'more',
    'most', 'other', 'some', 'such', 'than', 'too', 'very', 'just',
    'about', 'above', 'after', 'all', 'also', 'am', 'any', 'because',
    'before', 'between', 'during', 'he', 'her', 'him', 'his', 'how',
    'i', 'into', 'me', 'my', 'our', 'out', 'own', 'same', 'she',
    'their', 'them', 'then', 'there', 'they', 'through', 'under', 'until',
    'up', 'us', 'we', 'what', 'when', 'where', 'which', 'while',
    'who', 'whom', 'why', 'you', 'your',
}

# ---------------------------------------------------------------------------
# Minimal Porter Stemmer (rule-based, standard library only)
# ---------------------------------------------------------------------------
_VOWELS = set('aeiou')

def _has_vowel(stem):
    return any(c in _VOWELS for c in stem)

def _ends_cvc(word):
    """True if word ends with consonant-vowel-consonant, and last consonant is not w/x/y."""
    if len(word) < 3:
        return False
    c1, v, c2 = word[-3], word[-2], word[-1]
    return (c1 not in _VOWELS and v in _VOWELS and
            c2 not in _VOWELS and c2 not in 'wxy')

def porter_stem(word):
    """
    Simplified Porter stemmer covering the most impactful rules.
    Operates on lowercase words.
    """
    if len(word) <= 2:
        return word

    # Step 1a
    if word.endswith('sses'):
        word = word[:-2]
    elif word.endswith('ies'):
        word = word[:-2]
    elif word.endswith('ss'):
        pass
    elif word.endswith('s'):
        word = word[:-1]

    # Step 1b
    if word.endswith('eed'):
        if len(word[:-3]) > 0:
            word = word[:-1]
    elif word.endswith('ed'):
        stem = word[:-2]
        if _has_vowel(stem):
            word = stem
            if word.endswith('at') or word.endswith('bl') or word.endswith('iz'):
                word += 'e'
            elif (len(word) > 1 and word[-1] == word[-2] and word[-1] not in 'lsz'):
                word = word[:-1]
    elif word.endswith('ing'):
        stem = word[:-3]
        if _has_vowel(stem):
            word = stem
            if word.endswith('at') or word.endswith('bl') or word.endswith('iz'):
                word += 'e'
            elif (len(word) > 1 and word[-1] == word[-2] and word[-1] not in 'lsz'):
                word = word[:-1]

    # Step 1c
    if word.endswith('y') and _has_vowel(word[:-1]):
        word = word[:-1] + 'i'

    # Step 2 (most common suffixes)
    step2_map = {
        'ational': 'ate', 'tional': 'tion', 'enci': 'ence',
        'anci': 'ance', 'izer': 'ize', 'abli': 'able',
        'alli': 'al',   'entli': 'ent', 'eli': 'e',
        'ousli': 'ous', 'ization': 'ize', 'ation': 'ate',
        'ator': 'ate',  'alism': 'al',   'iveness': 'ive',
        'fulness': 'ful', 'ousness': 'ous', 'aliti': 'al',
        'iviti': 'ive', 'biliti': 'ble',
    }
    for suffix, replacement in step2_map.items():
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if len(stem) > 0:
                word = stem + replacement
            break

    # Step 3
    step3_map = {
        'icate': 'ic', 'ative': '', 'alize': 'al',
        'iciti': 'ic', 'ical': 'ic', 'ful': '', 'ness': '',
    }
    for suffix, replacement in step3_map.items():
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if len(stem) > 0:
                word = stem + replacement
            break

    # Step 4 (remove derivational suffixes)
    step4_list = [
        'ement', 'ment', 'ance', 'ence', 'able', 'ible',
        'ant',   'ent',  'ion',  'ism',  'ate',  'iti',
        'ous',   'ive',  'ize',  'al',   'er',   'ic',
    ]
    for suffix in step4_list:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if len(stem) > 1:
                word = stem
            break

    # Step 5a
    if word.endswith('e'):
        stem = word[:-1]
        if len(stem) > 1:
            word = stem
        elif len(stem) == 1 and not _ends_cvc(stem):
            word = stem

    # Step 5b
    if len(word) > 1 and word.endswith('ll') and len(word) > 2:
        word = word[:-1]

    return word


def tokenize(text):
    """
    Lowercase, strip punctuation/numbers, remove stopwords, apply stemming.
    Returns a list of processed tokens.
    """
    # lowercase & strip non-alpha characters
    tokens = re.findall(r'[a-z]+', text.lower())
    result = []
    for t in tokens:
        if len(t) > 1 and t not in STOPWORDS:
            stemmed = porter_stem(t)
            if len(stemmed) > 1:
                result.append(stemmed)
    return result
