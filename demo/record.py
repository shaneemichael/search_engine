"""
Records the Scalpel demo video: drives the web app through the DEMO.md scenes
in headless Chromium, captures frames over the DevTools screencast and
encodes them to MP4.

    pip install playwright==1.52.0 imageio-ffmpeg==0.6.0
    python -m playwright install chromium
    python demo/record.py [BASE_URL]

The video is written to demo/out/scalpel-demo.mp4.
"""
import asyncio
import base64
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.async_api import async_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://search-engine-nine-sepia.vercel.app").rstrip("/")
OUT = Path(__file__).parent / "out" / "scalpel-demo.mp4"
VIEWPORT = {"width": 1600, "height": 900}
SCALE = 1.2  # 1600x900 CSS pixels -> 1920x1080 video
FPS = 30

OVERLAY_JS = r"""
(() => {
  const ready = () => {
    if (document.getElementById('demo-cursor')) return;
    const style = document.createElement('style');
    style.textContent = `
      #demo-cursor{position:fixed;left:-40px;top:-40px;width:24px;height:24px;z-index:2147483647;pointer-events:none;transform-origin:3px 2px;transition:transform .1s}
      #demo-cursor.down{transform:scale(.82)}
      .demo-ripple{position:fixed;width:40px;height:40px;margin:-20px 0 0 -20px;border-radius:50%;border:2.5px solid #0f766e;z-index:2147483646;pointer-events:none;animation:demo-ripple .55s ease-out forwards}
      @keyframes demo-ripple{from{transform:scale(.3);opacity:.9}to{transform:scale(1.5);opacity:0}}
      #demo-caption{position:fixed;left:50%;bottom:32px;transform:translate(-50%,14px);z-index:2147483645;max-width:1180px;padding:14px 26px;border-radius:14px;background:rgba(22,24,29,.9);color:#fff;font:500 20px/1.45 Inter,system-ui,sans-serif;text-align:center;box-shadow:0 18px 50px -12px rgba(0,0,0,.45);opacity:0;transition:opacity .4s,transform .4s;pointer-events:none}
      #demo-caption.show{opacity:1;transform:translate(-50%,0)}
      #demo-caption b{color:#7fe0cf;font-weight:600}
      #demo-card{position:fixed;inset:0;z-index:2147483644;background:#f6f5f1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;opacity:0;transition:opacity .7s;pointer-events:none}
      #demo-card.show{opacity:1}
      #demo-card .logo{display:flex;align-items:center;gap:18px;font:104px/1 'Instrument Serif',serif;color:#16181d;letter-spacing:-.02em}
      #demo-card .logo svg{width:84px;height:84px}
      #demo-card p{font:400 24px Inter,sans-serif;color:#464a55;margin:0}
      #demo-card p em{font:italic 30px 'Instrument Serif',serif;color:#0f766e}
      #demo-card .tags{display:flex;flex-wrap:wrap;justify-content:center;gap:10px;margin-top:14px;max-width:1000px}
      #demo-card .tags span{font:500 16px Inter,sans-serif;padding:8px 16px;border-radius:99px;background:#fff;border:1px solid #e8e5dd;color:#464a55}
    `;
    document.head.appendChild(style);
    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24"><path d="M3 2l7.5 19 2.6-7.6L21 10.8z" fill="#16181d" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    const caption = document.createElement('div');
    caption.id = 'demo-caption';
    const card = document.createElement('div');
    card.id = 'demo-card';
    document.body.append(cursor, caption, card);
    document.addEventListener('mousemove', (e) => { cursor.style.left = `${e.clientX}px`; cursor.style.top = `${e.clientY}px`; }, true);
    document.addEventListener('mousedown', (e) => {
      cursor.classList.add('down');
      const r = document.createElement('div');
      r.className = 'demo-ripple';
      r.style.left = `${e.clientX}px`; r.style.top = `${e.clientY}px`;
      document.body.appendChild(r);
      setTimeout(() => r.remove(), 700);
    }, true);
    document.addEventListener('mouseup', () => cursor.classList.remove('down'), true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready);
  else ready();
})();
"""

LOGO_SVG = ('<svg viewBox="0 0 32 32"><circle cx="13" cy="13" r="9" fill="none" stroke="#0f766e" stroke-width="2.6"/>'
            '<path d="M9 13.5c1.4-3 4.6-4.4 7.4-3.4" fill="none" stroke="#0f766e" stroke-width="2" stroke-linecap="round" opacity=".45"/>'
            '<path d="M20 20l8 8" stroke="#16181d" stroke-width="3.4" stroke-linecap="round"/></svg>')


TITLE_CARD = f'<div class="logo">{LOGO_SVG}Scalpel</div><p>A search engine, <em>built from scratch.</em></p>'


class Screencast:
    """Collects DevTools screencast frames with their timestamps."""

    def __init__(self, cdp, frames_dir):
        self.cdp = cdp
        self.dir = frames_dir
        self.frames = []
        cdp.on("Page.screencastFrame", self._on_frame)

    def _on_frame(self, params):
        path = self.dir / f"{len(self.frames):06d}.jpg"
        path.write_bytes(base64.b64decode(params["data"]))
        self.frames.append((path, params["metadata"]["timestamp"]))
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}))

    async def start(self):
        await self.cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": 95, "everyNthFrame": 1,
            "maxWidth": int(VIEWPORT["width"] * SCALE), "maxHeight": int(VIEWPORT["height"] * SCALE),
        })

    async def stop(self):
        await self.cdp.send("Page.stopScreencast")
        self.end = time.time()

    def encode(self, out_path):
        listing = self.dir / "frames.txt"
        lines = []
        for (path, ts), nxt in zip(self.frames, self.frames[1:] + [(None, self.end)]):
            lines.append(f"file '{path.name}'\nduration {max(nxt[1] - ts, 0.001):.4f}")
        lines.append(f"file '{self.frames[-1][0].name}'")
        listing.write_text("\n".join(lines))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-vf", f"fps={FPS},scale=1920:1080:flags=lanczos:in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-color_range", "tv",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-movflags", "+faststart",
            str(out_path),
        ], check=True)


class Director:
    def __init__(self, page):
        self.page = page
        self.x, self.y = VIEWPORT["width"] / 2, VIEWPORT["height"] / 2

    async def wait(self, seconds):
        await asyncio.sleep(seconds)

    async def glide(self, x, y, duration=0.7):
        steps = max(int(duration * 60), 1)
        x0, y0 = self.x, self.y
        for i in range(1, steps + 1):
            t = i / steps
            e = 1 - (1 - t) ** 3  # ease-out cubic
            await self.page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
            await asyncio.sleep(duration / steps)
        self.x, self.y = x, y

    async def box(self, selector):
        el = self.page.locator(selector).first
        await el.wait_for(state="visible", timeout=60000)
        return await el.bounding_box()

    async def hover(self, selector, duration=0.7, fx=0.5, fy=0.5):
        await self.reveal(selector)
        b = await self.box(selector)
        await self.glide(b["x"] + b["width"] * fx, b["y"] + b["height"] * fy, duration)

    async def click(self, selector, duration=0.7, fx=0.5, fy=0.5):
        await self.hover(selector, duration, fx, fy)
        await asyncio.sleep(0.15)
        await self.page.mouse.down()
        await asyncio.sleep(0.08)
        await self.page.mouse.up()

    async def reveal(self, selector, block="center"):
        """Smooth-scrolls `selector` into view when it is not already fully visible."""
        visible = await self.page.locator(selector).first.evaluate(
            "(el) => { const r = el.getBoundingClientRect(); return r.top >= 70 && r.bottom <= innerHeight - 110; }")
        if not visible:
            await self.scroll_to(selector, block)

    async def scroll_to(self, selector, block="center"):
        await self.page.locator(selector).first.evaluate(
            f"(el) => el.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
        await asyncio.sleep(1.1)

    async def type(self, selector, text):
        await self.click(selector)
        await self.page.keyboard.press("Control+A")
        await self.page.keyboard.type(text, delay=70)

    async def caption(self, html, hold=0.0):
        await self.page.evaluate("""(html) => {
            const c = document.getElementById('demo-caption');
            c.classList.remove('show');
            if (html) setTimeout(() => { c.innerHTML = html; c.classList.add('show'); }, 180);
        }""", html)
        await asyncio.sleep(hold)

    async def show_card(self, html, instant=False):
        await self.page.evaluate("""([html, instant]) => {
            const c = document.getElementById('demo-card');
            c.innerHTML = html;
            if (instant) c.style.transition = 'none';
            c.classList.add('show');
            document.getElementById('demo-cursor').style.opacity = '0';
            requestAnimationFrame(() => requestAnimationFrame(() => { c.style.transition = ''; }));
        }""", [html, instant])

    async def hide_card(self):
        await self.page.evaluate("""() => {
            document.getElementById('demo-card').classList.remove('show');
            document.getElementById('demo-cursor').style.opacity = '1';
        }""")
        await asyncio.sleep(0.8)


async def facts(request):
    """Numbers quoted in captions, read from the live API so the video never misstates them."""
    overview = await (await request.get(f"{BASE}/api/overview", timeout=120000)).json()
    for config in await (await request.get(f"{BASE}/api/configs", timeout=120000)).json():
        if not config["built"]:
            print(f"  building {config['key']} on the server …")
            await request.post(f"{BASE}/api/configs/{config['key']}/build", timeout=180000)
    text = {q["id"]: q["text"] for q in overview["queries"]}
    q3 = await (await request.get(f"{BASE}/api/search", params={"q": text["Q3"], "method": "adaptive"}, timeout=120000)).json()
    q3_wand = await (await request.get(f"{BASE}/api/search", params={"q": text["Q3"], "method": "wand"}, timeout=120000)).json()
    q9 = await (await request.get(f"{BASE}/api/compare", params={"q": text["Q9"]}, timeout=120000)).json()
    ev = await (await request.get(f"{BASE}/api/evaluation", timeout=180000)).json()
    configs = await (await request.get(f"{BASE}/api/configs", timeout=120000)).json()
    await request.get(f"{BASE}/api/postings", params={"term": "cancer"}, timeout=120000)
    await request.get(f"{BASE}/api/postings", params={"term": "iodoacetate"}, timeout=120000)

    relevant = lambda results: sum(1 for r in results if r["relevant"])
    runs = {r["method"]: relevant(r["results"]) for r in q9["runs"]}
    best, base = ev["runs"][-1], ev["runs"][1]
    wins = sum(1 for q in best["per_query"] if best["per_query"][q]["ap"] - base["per_query"][q]["ap"] > 0.005)
    sizes = {c["compression"]: c["sizes"]["postings"] for c in configs if c["key"].startswith("spimi-patricia") and c["built"]}
    stats = q3_wand["stats"]
    return {
        "q3_rel": relevant(q3["results"]),
        "wand_pct": round(100 * stats["scored"] / stats["candidates"]),
        "q9_lex": runs["bm25"], "q9_adaptive": runs["adaptive"],
        "map": best["mean"]["ap"], "map_gain": (best["mean"]["ap"] / base["mean"]["ap"] - 1) * 100,
        "wins": wins, "queries": len(best["per_query"]),
        "vbe_x": sizes["standard"] / sizes["vbe"], "elias_x": sizes["standard"] / sizes["elias"],
    }


async def scenes(d, f):
    page = d.page

    # --- Title (shown before recording starts) -------------------------------
    await d.wait(3.4)
    await d.hide_card()

    # --- Search --------------------------------------------------------------
    await d.caption("A search engine built from scratch over <b>1,033 MEDLINE medical abstracts</b>. No IR libraries.", 0.4)
    await d.hover("#hero-stats", 1.2)
    await d.wait(3.0)
    await d.caption("Start with one of the <b>30 benchmark queries</b>. Every result is checked against human relevance labels.", 0.6)
    await d.hover('.chip[data-id="Q3"]', 1.0)
    await d.wait(1.6)
    await d.click('.chip[data-id="Q3"]', 0.3)
    await page.locator(".result").first.wait_for()
    await d.wait(1.4)
    await d.caption("Queries go through the same pipeline as documents: <b>stopword removal</b> and <b>Porter stemming</b>.", 0.4)
    await d.hover("#search-analysis .tok:nth-of-type(3)", 1.0)
    await d.wait(1.0)
    await d.hover("#search-analysis .tok:last-of-type", 1.2)
    await d.wait(2.0)
    await d.caption(f"<b>{f['q3_rel']} of the top 10</b> results are judged relevant.", 0.4)
    await d.hover("#search-meta .bench", 1.0)
    await d.wait(1.4)
    await d.hover(".result:first-child .badge", 1.0)
    await d.wait(2.2)

    await d.caption(f"With <b>BM25 + WAND</b>, upper-bound pruning fully scores only <b>{f['wand_pct']}%</b> of the candidate documents.", 0.4)
    await d.click('#method-switch button[data-method="wand"]', 1.0)
    await page.locator("#search-meta .prune").wait_for()
    await d.wait(0.6)
    await d.hover("#search-meta .prune-bar", 1.0)
    await d.wait(3.4)

    await d.caption("Click a result to read the full document, with the query terms highlighted.", 0.4)
    await d.click(".result:nth-child(2) h3", 1.0)
    await d.wait(1.2)
    await d.hover("#drawer-body mark", 1.0)
    await d.wait(2.6)
    await d.click("#drawer-close", 0.8)
    await d.wait(0.6)

    await d.caption("Or type your own query.", 0.2)
    await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    await d.wait(0.8)
    await d.click('#method-switch button[data-method="adaptive"]', 0.8)
    await d.wait(0.8)
    await d.type("#search-input", "high blood pressure during pregnancy")
    await d.wait(0.3)
    await page.keyboard.press("Enter")
    await d.wait(1.2)
    await page.evaluate("window.scrollBy({top: 380, behavior: 'smooth'})")
    await d.wait(2.4)

    # --- Compare -------------------------------------------------------------
    await d.caption("<b>Compare</b>: the same query through four ranking models.", 0.2)
    await d.click('.tabs a[data-view="compare"]', 1.0)
    await page.locator(".bump .row").first.wait_for()
    await d.wait(2.2)
    await d.caption(f"Keyword models find <b>{f['q9_lex']}</b> relevant documents in the top 10. The BM25 + LSI hybrid finds <b>{f['q9_adaptive']}</b>.", 0.4)
    await d.hover(".scoreboard .sb:nth-child(2)", 1.0)
    await d.wait(1.6)
    await d.hover(".scoreboard .sb:nth-child(4)", 1.0)
    await d.wait(2.4)
    await d.caption("Lines trace each document across rankers. <b>Green</b> lines are relevant documents.", 0.2)
    await d.scroll_to(".bump", "start")
    await d.wait(0.6)
    targets = await page.locator('.col[data-col="3"] .row').evaluate_all(
        "rows => rows.map((r, i) => [i, !!r.querySelector('.delta.new, .delta.up')]).filter(x => x[1]).map(x => x[0])")
    for i in (targets or [1, 3])[:3]:
        await d.hover(f'.col[data-col="3"] .row >> nth={i}', 0.9, fx=0.4)
        await d.wait(1.9)
    await d.hover('.col[data-col="0"] .row >> nth=0', 1.1, fx=0.4)
    await d.wait(2.0)

    # --- Index Lab -----------------------------------------------------------
    await d.caption("<b>Index Lab</b>: what the inverted index looks like on disk.", 0.2)
    await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    await d.wait(0.8)
    await d.click('.tabs a[data-view="lab"]', 1.0)
    await page.locator(".codec").first.wait_for()
    await d.wait(1.6)
    await d.caption(f"Gap encoding shrinks the postings file: Variable-Byte <b>{f['vbe_x']:.1f}× smaller</b>, Elias-Gamma <b>{f['elias_x']:.1f}× smaller</b>.", 0.4)
    await d.hover(".codec:nth-child(2) .size", 1.0)
    await d.wait(1.8)
    await d.hover(".codec:nth-child(3) .size", 1.0)
    await d.wait(2.2)

    await d.caption("The postings inspector shows how each codec writes a term's doc-ID gaps, <b>bit by bit</b>.", 0.2)
    await d.scroll_to("#inspector-body .ptable", "center")
    await d.hover("#inspector-body tbody tr:nth-child(6) td:nth-child(6)", 1.0)
    await d.wait(2.0)
    await d.hover("#inspector-body tbody tr:nth-child(6) td:nth-child(7)", 1.0)
    await d.wait(2.4)
    await d.caption("Small gaps get tiny Elias-Gamma codes, so it wins on frequent terms like <b>cancer</b>…", 0.2)
    await d.hover("#inspector-body .bytes-row >> nth=2", 1.0, fx=0.3)
    await d.wait(2.8)
    await d.caption("…but half the vocabulary appears in one document, and each Elias-Gamma list pays a <b>4-byte header</b>.", 0.2)
    await d.scroll_to("#inspector-form", "center")
    await d.type("#inspector-input", "iodoacetate")
    await page.keyboard.press("Enter")
    await d.wait(1.2)
    await d.scroll_to("#inspector-body .bytes-row", "center")
    await d.hover("#inspector-body .bytes-row >> nth=1", 1.0, fx=0.3)
    await d.wait(3.2)

    await d.caption("Nine real indexes: <b>indexer × dictionary × codec</b>. Each one rebuilds live in seconds.", 0.2)
    await d.scroll_to("#matrix", "center")
    await d.wait(1.0)
    cell = '.cell[data-key="spimi-patricia-elias"]'
    await d.click(f"{cell} .rebuild", 1.2)
    await page.locator(f"{cell}.flash").wait_for(timeout=120000)
    await d.wait(2.4)

    # --- Evaluation ----------------------------------------------------------
    await d.caption("<b>Evaluation</b>: 30 queries, 4 metrics, 5 retrieval setups.", 0.2)
    await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    await d.wait(0.8)
    await d.click('.tabs a[data-view="evaluation"]', 1.0)
    await page.locator(".kpi").first.wait_for(timeout=180000)
    await d.wait(1.6)
    await d.caption(f"The hybrid leads on every metric: MAP <b>{f['map']:.3f}</b>, <b>+{f['map_gain']:.1f}%</b> over BM25.", 0.4)
    await d.hover(".kpi:first-child .v", 1.0)
    await d.wait(3.0)
    await d.scroll_to("#grouped-chart", "center")
    await d.wait(2.6)
    await d.scroll_to("#leader", "center")
    await d.hover("#leader tr.best td:first-child", 1.0)
    await d.wait(2.4)
    await d.caption(f"Per query, the hybrid is better on <b>{f['wins']} of {f['queries']}</b>. Hover a bar for details.", 0.2)
    await d.scroll_to("#per-query-chart", "center")
    await d.hover('.qbar[data-id="Q20"] rect.bar', 1.0)
    await d.wait(2.6)
    await d.hover('.qbar[data-id="Q10"] rect.bar', 1.4)
    await d.wait(2.6)
    await d.caption("Click a bar to open that query in Compare.", 0.2)
    await d.click('.qbar[data-id="Q9"] rect.bar', 1.0)
    await page.locator(".bump .row").first.wait_for()
    await d.wait(2.8)
    await d.caption("", 0.4)

    # --- Outro ---------------------------------------------------------------
    tags = "".join(f"<span>{t}</span>" for t in [
        "BSBI & SPIMI indexing", "Trie & Patricia dictionaries", "VByte & Elias-Gamma",
        "TF-IDF · BM25 · WAND", "LSI + FAISS hybrid", "RBP · DCG · NDCG · MAP"])
    await d.show_card(f'<div class="logo">{LOGO_SVG}Scalpel</div><p>A search engine, <em>built from scratch.</em></p><div class="tags">{tags}</div>')
    await d.wait(4.5)


async def main():
    frames_dir = Path(tempfile.mkdtemp(prefix="scalpel-frames-"))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)
        await context.add_init_script(OVERLAY_JS)
        page = await context.new_page()

        print(f"Warming up {BASE} …")
        f = await facts(context.request)
        print("Caption facts:", {k: round(v, 3) if isinstance(v, float) else v for k, v in f.items()})

        await page.goto(f"{BASE}/#search", wait_until="networkidle")
        await page.evaluate("document.fonts.ready")
        await page.mouse.move(VIEWPORT["width"] / 2, VIEWPORT["height"] / 2)
        await asyncio.sleep(1.0)

        director = Director(page)
        await director.show_card(TITLE_CARD, instant=True)
        await asyncio.sleep(0.5)
        cast = Screencast(await context.new_cdp_session(page), frames_dir)
        await cast.start()
        await scenes(director, f)
        await cast.stop()
        await browser.close()

    print(f"Encoding {len(cast.frames)} frames …")
    cast.encode(OUT)
    shutil.rmtree(frames_dir, ignore_errors=True)
    print(f"Saved {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {cast.end - cast.frames[0][1]:.0f} s)")


if __name__ == "__main__":
    asyncio.run(main())
