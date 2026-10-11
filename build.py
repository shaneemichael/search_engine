import argparse

from engine import ALL_CONFIGS, COMPRESSIONS, IndexConfig, build


def main():
    parser = argparse.ArgumentParser(description="Build inverted indices (and their LSI models)")
    parser.add_argument("--index", choices=["bsbi", "spimi"], default="spimi", help="Indexing algorithm")
    parser.add_argument("--dictionary", choices=["standard", "trie", "patricia"], default="patricia",
                        help="Term dictionary (bsbi: standard; spimi: trie or patricia)")
    parser.add_argument("--compression", choices=list(COMPRESSIONS), default="elias", help="Postings compression")
    parser.add_argument("--all", action="store_true", help="Build every supported configuration")
    parser.add_argument("--no-lsi", action="store_true", help="Skip the LSI/FAISS semantic model")
    args = parser.parse_args()

    configs = ALL_CONFIGS if args.all else [IndexConfig(args.index, args.dictionary, args.compression)]
    for config in configs:
        print(f"Building {config.label}  ->  {config.directory}")
        meta = build(config, with_lsi=not args.no_lsi)
        sizes = config.file_sizes()
        lsi = f", LSI {meta['lsi_seconds']:.2f}s" if 'lsi_seconds' in meta else ""
        print(f"  {meta['terms']} terms, {meta['docs']} docs, postings {sizes['postings'] / 1024:.1f} KiB, "
              f"index {meta['index_seconds']:.2f}s{lsi}\n")


if __name__ == '__main__':
    main()
