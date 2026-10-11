# Demo video script (~5 minutes)

## Before recording

1. `python build.py --all`, then `python -m web`.
2. Open `http://127.0.0.1:8000` in a clean browser window (no bookmarks bar, no extensions in the toolbar), 1920×1080, page zoom 110–125%.
3. Warm everything up once: open **Evaluation** (the first load runs 150 queries) and **Compare**, then go back to `http://127.0.0.1:8000/#search`.
4. Move the cursor slowly and pause ~1 s after each click so the animations finish on camera.

Every view has a shareable URL, so a scene can be re-shot by opening its link directly.

---

## 1. Intro: Search home (0:00–0:25)

**Show:** the landing page. Hover the stats row.

> "This is Scalpel, a search engine we built from scratch over the MEDLINE collection: 1,033 medical abstracts. Indexing, compression, ranking and semantic search are all our own code, with no IR libraries."

## 2. First search and the text pipeline (0:25–1:05)

**Do:** click the chip **Q3 electron microscopy of lung or bronchi**.

**Point at:** the *Query terms* row (stopwords crossed out, `microscopy → microscopi`), then the result cards, the green **✓ Relevant** badges, and the benchmark pill (`9/10 relevant`).

> "Each query goes through the same pipeline as the documents: lowercasing, stopword removal and Porter stemming. Q3 is one of the 30 benchmark queries, so every result is checked against the human relevance judgments. Nine of the top ten are relevant."

**Do:** click the **BM25 + WAND** ranking tab.

> "With WAND, the engine fully scored only about half of the candidate documents. The rest were skipped because their score upper bound could never reach the top ten. Same top ten as BM25, less work."

**Do:** click the first result to open the document drawer, then press Esc.

## 3. Compare rankers (1:05–2:05)

**Do:** open the **Compare** tab (it preloads Q9, *induced hypothermia in heart surgery…*).

**Point at:** the scoreboard: TF-IDF, BM25 and WAND each get 5/10 relevant, Adaptive gets 8/10.

> "Here's the same query through all four ranking models. Lexical models only reward exact term matches. The adaptive model fuses BM25 with Latent Semantic Indexing: an SVD of the term-document matrix searched through FAISS, so it also finds documents about the same concept in different words."

**Do:** hover a document in the Adaptive column that has a **NEW** badge, then hover one that moves up (▲) between columns.

> "The lines trace each document across rankers. Green lines are relevant documents. The hybrid promotes relevant documents that keyword matching ranked lower or missed entirely."

## 4. Index Lab (2:05–3:35)

**Do:** open **Index Lab**.

> "Postings lists are stored compressed. Variable-Byte shrinks the postings file to about a quarter of its raw size, and Elias-Gamma to about a third."

**Do:** in the inspector, the term `cancer` is preloaded. Point along one row of the table.

> "Doc IDs are stored as gaps between neighbours. Variable-Byte writes seven data bits per byte; the blue bit marks the last byte. Elias-Gamma writes the length in unary (orange), a separator, then the binary offset. Small gaps get tiny codes, so for `cancer` Elias-Gamma is the smallest at 99 bytes."

**Do:** type `iodoacetate` → **Inspect** (a rare term: 2 postings).

> "So why is VByte smaller overall? Half our vocabulary appears in just one document. Every Elias-Gamma list starts with a 4-byte length header, so a rare term like this costs 12 bytes versus 5 for VByte, and across four thousand rare terms that adds up to the whole difference."

**Do:** scroll to the **Build matrix**. Click **Rebuild** on *SPIMI · Patricia tree · Elias-Gamma* and let the progress bar finish.

> "There are nine real indexes on disk: BSBI or SPIMI indexing, three dictionary structures and three codecs. Each one rebuilds in about two seconds, including the semantic model."

## 5. Evaluation (3:35–4:40)

**Do:** open **Evaluation**. Pause on the KPI tiles, then scroll to the chart.

> "We evaluated five setups on all 30 queries with four metrics. The hybrid model leads on every one: MAP 0.706, up 20.7% over BM25."

**Do:** scroll to **Where the hybrid helps** and hover the tallest bar (Q20), then a blue one.

> "Per query, the hybrid is better on 25 of 30. It isn't free, though: on a few queries the semantic signal pulls in off-topic documents."

**Do:** click the Q9 bar to jump back into Compare.

## 6. Close (4:40–5:00)

**Show:** the Search home again.

> "That's Scalpel: inverted indexes, compression, ranking with pruning, semantic retrieval and evaluation, all built from the ground up."
