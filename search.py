import argparse

from engine import COMPRESSIONS, METHODS, IndexConfig, SearchEngine
from retrieval import read_document, snippet

DEFAULT_QUERIES = [
    "alkylated with radioactive iodoacetate",
    "psychodrama for disturbed children",
    "lipid metabolism in toxemia and normal pregnancy",
]


def render_snippet(query, doc_path):
    segments = snippet(query, read_document(doc_path))
    rendered = "".join(f"\033[1;33m{text}\033[0m" if hit else text for text, hit in segments)
    return rendered.replace("…", "...")


def main():
    parser = argparse.ArgumentParser(description="Search Engine CLI")
    parser.add_argument("query", nargs='?', default=None, help="The query string to search for")
    parser.add_argument("--index", choices=["bsbi", "spimi"], default="spimi", help="Indexing algorithm")
    parser.add_argument("--dictionary", choices=["standard", "trie", "patricia"], default="patricia",
                        help="Term dictionary (bsbi: standard; spimi: trie or patricia)")
    parser.add_argument("--compression", choices=list(COMPRESSIONS), default="elias", help="Postings compression")
    parser.add_argument("--metric", choices=[*METHODS, "all"], default="all", help="Retrieval method")
    parser.add_argument("-k", type=int, default=5, help="Number of results per method")
    parser.add_argument("--snippets", action="store_true", help="Show highlighted context snippets")
    args = parser.parse_args()

    config = IndexConfig(args.index, args.dictionary, args.compression)
    engine = SearchEngine(config)
    methods = list(METHODS) if args.metric == "all" else [args.metric]

    print(f"Index: {config.label}")
    for query in [args.query] if args.query else DEFAULT_QUERIES:
        print(f"\n{'=' * 60}\nQuery: {query}\n{'=' * 60}")
        for method in methods:
            print(f"\n[{METHODS[method]}]")
            for score, doc in engine.search(method, query, k=args.k):
                print(f"  {doc:45s} {score:>8.4f}")
                if args.snippets:
                    print(f"    {render_snippet(query, doc)}")


if __name__ == '__main__':
    main()
