'use strict';

const METHOD_COLORS = {
  tfidf: 'var(--m-tfidf)', bm25: 'var(--m-bm25)', wand: 'var(--m-wand)', adaptive: 'var(--m-adaptive)',
};
const METHOD_DESC = {
  tfidf: '(1 + log tf) · log(N / df)',
  bm25: 'k₁ = 1.2, b = 0.75',
  wand: 'BM25, pruned with upper bounds',
  adaptive: 'BM25-WAND fused with LSI cosine',
};
const CODEC_INFO = {
  standard: { name: 'Uncompressed', color: '#a3a6ae', how: 'Fixed-width integers: every doc ID and term frequency takes 4 bytes.' },
  vbe: { name: 'Variable-Byte', color: 'var(--m-bm25)', how: 'Doc-ID gaps, 7 data bits per byte plus a continuation flag.' },
  elias: { name: 'Elias-Gamma', color: 'var(--m-tfidf)', how: 'Doc-ID gaps, unary length prefix + binary offset, bit-packed.' },
};
const ROWS = [['bsbi', 'standard'], ['spimi', 'trie'], ['spimi', 'patricia']];
const RUN_COLORS = ['var(--m-tfidf)', 'var(--m-bm25)', 'var(--m-wand)', 'var(--m-wand2)', 'var(--m-adaptive)'];
const SUGGESTED = ['Q3', 'Q9', 'Q10', 'Q4'];
const COMPARE_DEFAULT = 'Q9';

const state = {
  overview: null,
  configs: null,
  method: 'adaptive',
  config: null,
  lastSearch: null,
  lastCompare: null,
  evaluation: null,
};

/* ---------------- helpers ---------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n, d = 0) => Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const kib = (bytes) => fmt(bytes / 1024, 1);
const segs = (segments) => segments.map(([t, hit]) => (hit ? `<mark>${esc(t)}</mark>` : esc(t))).join('');

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* not JSON */ }
    throw new Error(detail);
  }
  return res.json();
}

function queryText(qid) {
  const q = state.overview.queries.find((x) => x.id === qid);
  return q ? q.text : '';
}

function configLabel(c) { return c.labels.join(' · '); }

function fillConfigSelect(select, value) {
  select.innerHTML = state.configs.map((c) =>
    `<option value="${c.key}" ${c.key === value ? 'selected' : ''}>${esc(configLabel(c))}</option>`).join('');
}

const tooltip = $('#tooltip');
function showTip(html, evt) {
  tooltip.innerHTML = html;
  tooltip.classList.add('show');
  const pad = 14;
  const { innerWidth: w } = window;
  const rect = tooltip.getBoundingClientRect();
  let x = evt.clientX + pad;
  if (x + rect.width > w - 8) x = evt.clientX - rect.width - pad;
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${evt.clientY + pad}px`;
}
function hideTip() { tooltip.classList.remove('show'); }

/* ---------------- routing ---------------- */
function parseHash() {
  const [view, qs] = location.hash.replace(/^#/, '').split('?');
  return { view: view || 'search', params: new URLSearchParams(qs || '') };
}

function setHash(view, params) {
  const qs = new URLSearchParams(params).toString();
  const next = `#${view}${qs ? `?${qs}` : ''}`;
  if (location.hash !== next) location.hash = next;
  else route();
}

let currentView = null;

function route() {
  const { view, params } = parseHash();
  if (view !== currentView) {
    currentView = view;
    window.scrollTo(0, 0);
  }
  document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${view}`));
  document.querySelectorAll('.tabs a').forEach((a) => a.classList.toggle('active', a.dataset.view === view));
  if (view === 'search') routeSearch(params);
  if (view === 'compare') routeCompare(params);
  if (view === 'lab') loadLab();
  if (view === 'evaluation') loadEvaluation();
}

/* ---------------- search ---------------- */
function renderMethodSwitch() {
  $('#method-switch').innerHTML = Object.entries(state.overview.methods).map(([key, label]) =>
    `<button type="button" data-method="${key}" class="${key === state.method ? 'active' : ''}">
       <span class="swatch" style="background:${METHOD_COLORS[key]}"></span>${esc(label)}</button>`).join('');
}

function routeSearch(params) {
  const q = params.get('q');
  state.method = params.get('m') || state.method;
  state.config = params.get('c') || state.config;
  renderMethodSwitch();
  fillConfigSelect($('#search-config'), state.config);
  const shell = $('#search-shell');
  if (!q) {
    shell.classList.remove('compact');
    $('#search-body').hidden = true;
    $('#search-input').value = '';
    return;
  }
  $('#search-input').value = q;
  shell.classList.add('compact');
  $('#search-body').hidden = false;
  const key = `${q}|${state.method}|${state.config}`;
  if (state.lastSearch !== key) {
    state.lastSearch = key;
    runSearch(q);
  }
}

function submitSearch(q) {
  q = q.trim();
  if (!q) return;
  setHash('search', { q, m: state.method, c: state.config });
}

function renderAnalysis(el, analysis) {
  el.innerHTML = `<span class="tag">Query terms</span>` + analysis.map((t, i) =>
    `<span class="tok ${t.stem ? '' : 'drop'}" style="animation-delay:${i * 35}ms">
       <span class="w">${esc(t.word)}</span><span class="s">${t.stem ? esc(t.stem) : 'stop'}</span></span>`).join('');
}

async function runSearch(q) {
  const results = $('#results');
  results.innerHTML = Array.from({ length: 4 }, () => '<div class="skeleton"></div>').join('');
  $('#search-meta').innerHTML = '';
  try {
    const params = new URLSearchParams({ q, method: state.method, config: state.config, k: 10 });
    const data = await api(`/api/search?${params}`);
    renderAnalysis($('#search-analysis'), data.analysis);
    renderSearchMeta(data);
    renderResults(data);
  } catch (e) {
    results.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function renderSearchMeta(data) {
  const parts = [`<span><b class="num">${data.results.length}</b> results in <b class="num">${fmt(data.elapsed_ms, 1)} ms</b></span>`];
  if (data.stats && data.stats.candidates) {
    const { scored, candidates } = data.stats;
    const pruned = 1 - scored / candidates;
    parts.push(`<span class="prune">WAND fully scored <b class="num">${scored}</b> of <b class="num">${candidates}</b> candidates
      <span class="prune-bar"><i style="width:${(scored / candidates) * 100}%"></i></span><b class="num">${fmt(pruned * 100)}%</b> skipped</span>`);
  }
  if (data.benchmark) {
    const rel = data.results.filter((r) => r.relevant).length;
    parts.push(`<span class="pill bench">Benchmark ${data.benchmark.id} · <b class="num">${rel}/${data.results.length}</b> relevant · ${data.benchmark.relevant_total} judged relevant</span>`);
  }
  $('#search-meta').innerHTML = parts.join('');
}

function relBadge(relevant) {
  if (relevant === true) return '<span class="badge rel">✓ Relevant</span>';
  if (relevant === false) return '<span class="badge non">Not judged relevant</span>';
  return '';
}

function renderResults(data) {
  const results = $('#results');
  if (!data.results.length) {
    results.innerHTML = `<div class="empty">No documents match. Every query term was a stopword or is missing from the collection.</div>`;
    return;
  }
  const max = Math.max(...data.results.map((r) => r.score)) || 1;
  const color = METHOD_COLORS[data.method];
  results.innerHTML = data.results.map((r, i) => `
    <article class="result" data-path="${esc(r.path)}" style="animation-delay:${i * 45}ms">
      <div class="rank num">${String(r.rank).padStart(2, '0')}</div>
      <div>
        <h3>${esc(r.title)}</h3>
        <div class="sub"><span class="mono">${esc(r.path)}</span>${relBadge(r.relevant)}</div>
      </div>
      <div class="scorebox">
        <div class="l">Score</div>
        <div class="v num">${fmt(r.score, 4)}</div>
        <div class="scorebar"><i style="width:${(r.score / max) * 100}%;background:${color};animation-delay:${200 + i * 45}ms"></i></div>
      </div>
      <div class="snip">${segs(r.snippet)}</div>
    </article>`).join('');
}

/* ---------------- document drawer ---------------- */
async function openDoc(path, q) {
  const drawer = $('#drawer');
  $('#drawer-title').textContent = '';
  $('#drawer-facts').innerHTML = '';
  $('#drawer-body').innerHTML = '<div class="loading-note"><span class="spinner"></span>Loading</div>';
  drawer.classList.add('open');
  drawer.setAttribute('aria-hidden', 'false');
  $('#scrim').classList.add('open');
  try {
    const doc = await api(`/api/document?${new URLSearchParams({ path, q: q || '' })}`);
    const hits = doc.segments.filter(([, hit]) => hit).length;
    $('#drawer-eyebrow').textContent = `Document ${doc.number}`;
    $('#drawer-title').textContent = doc.title;
    $('#drawer-facts').innerHTML = `
      <span class="mono">${esc(doc.path)}</span>
      <span>${fmt(doc.words)} words</span>
      ${q ? `<span>${hits} term matches</span>` : ''}
      ${relBadge(doc.relevant)}`;
    $('#drawer-body').innerHTML = segs(doc.segments);
    const first = $('#drawer-body mark');
    if (first) first.scrollIntoView({ block: 'center' });
  } catch (e) {
    $('#drawer-body').innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function closeDoc() {
  $('#drawer').classList.remove('open');
  $('#drawer').setAttribute('aria-hidden', 'true');
  $('#scrim').classList.remove('open');
}

/* ---------------- compare ---------------- */
function routeCompare(params) {
  const q = params.get('q') || queryText(COMPARE_DEFAULT);
  const config = params.get('c') || state.config;
  $('#compare-input').value = q;
  fillConfigSelect($('#compare-config'), config);
  const key = `${q}|${config}`;
  if (state.lastCompare !== key) {
    state.lastCompare = key;
    runCompare(q, config);
  } else {
    requestAnimationFrame(drawLinks);
  }
}

async function runCompare(q, config) {
  const body = $('#compare-body');
  body.innerHTML = '<div class="loading-note"><span class="spinner"></span>Ranking with all four models…</div>';
  try {
    const data = await api(`/api/compare?${new URLSearchParams({ q, config, k: 10 })}`);
    renderAnalysis($('#compare-analysis'), data.analysis);
    renderCompare(data);
  } catch (e) {
    body.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function renderCompare(data) {
  const q = data.query;
  const scoreboard = data.runs.map((run) => {
    const color = METHOD_COLORS[run.method];
    if (data.benchmark) {
      const rel = run.results.filter((r) => r.relevant).length;
      const dots = run.results.map((r) => `<i style="${r.relevant ? `background:${color}` : ''}"></i>`).join('');
      return `<div class="sb"><div class="top"><span class="swatch" style="background:${color}"></span>${esc(run.label)}</div>
        <div class="big num">${rel}<small>/ ${run.results.length} relevant</small></div><div class="dots">${dots}</div></div>`;
    }
    return `<div class="sb"><div class="top"><span class="swatch" style="background:${color}"></span>${esc(run.label)}</div>
      <div class="big num">${fmt(run.elapsed_ms, 1)}<small>ms</small></div></div>`;
  }).join('');

  const columns = data.runs.map((run, ci) => {
    const color = METHOD_COLORS[run.method];
    const prev = ci > 0 ? new Map(data.runs[ci - 1].results.map((r) => [r.path, r.rank])) : null;
    let desc = METHOD_DESC[run.method];
    if (run.stats && run.stats.candidates) desc = `scored ${run.stats.scored} of ${run.stats.candidates} docs`;
    const rows = run.results.map((r, i) => {
      let delta = '';
      if (prev) {
        if (!prev.has(r.path)) delta = '<span class="delta new">NEW</span>';
        else {
          const d = prev.get(r.path) - r.rank;
          if (d > 0) delta = `<span class="delta up">▲${d}</span>`;
          if (d < 0) delta = `<span class="delta down">▼${-d}</span>`;
        }
      }
      return `<div class="row ${r.relevant ? 'rel' : ''}" data-path="${esc(r.path)}" style="animation-delay:${ci * 60 + i * 30}ms">
        <div class="r num">${r.rank}</div>
        <div><div class="t">${esc(r.title)}</div><div class="d"><span class="mono">#${r.number}</span>${delta}</div></div>
      </div>`;
    }).join('');
    return `<div class="col" data-col="${ci}">
      <div class="col-head" style="border-color:${color}">
        <div class="name"><span class="swatch" style="background:${color}"></span>${esc(run.label)}<span class="time num">${fmt(run.elapsed_ms, 1)} ms</span></div>
        <div class="desc">${esc(desc)}</div>
      </div>${rows}</div>`;
  }).join('');

  $('#compare-body').innerHTML = `
    <div class="scoreboard">${scoreboard}</div>
    <div class="bump" id="bump"><svg class="links" id="links"></svg>${columns}</div>`;

  const bump = $('#bump');
  bump.dataset.query = q;
  bump.dataset.benchmark = data.benchmark ? '1' : '';
  bump.querySelectorAll('.row').forEach((row) => {
    row.addEventListener('mouseenter', () => {
      bump.classList.add('hovering');
      const path = row.dataset.path;
      bump.querySelectorAll('.row').forEach((r) => r.classList.toggle('on', r.dataset.path === path));
      bump.querySelectorAll('path').forEach((p) => p.classList.toggle('on', p.dataset.path === path));
    });
    row.addEventListener('mouseleave', () => {
      bump.classList.remove('hovering');
      bump.querySelectorAll('.on').forEach((el) => el.classList.remove('on'));
    });
    row.addEventListener('click', () => openDoc(row.dataset.path, q));
  });
  requestAnimationFrame(drawLinks);
}

function drawLinks() {
  const bump = $('#bump');
  if (!bump || !bump.offsetParent) return;
  const svg = $('#links');
  const base = bump.getBoundingClientRect();
  const cols = [...bump.querySelectorAll('.col')];
  const benchmark = !!bump.dataset.benchmark;
  let paths = '';
  for (let i = 0; i < cols.length - 1; i += 1) {
    const next = new Map([...cols[i + 1].querySelectorAll('.row')].map((r) => [r.dataset.path, r]));
    cols[i].querySelectorAll('.row').forEach((row) => {
      const target = next.get(row.dataset.path);
      if (!target) return;
      const a = row.getBoundingClientRect();
      const b = target.getBoundingClientRect();
      const x1 = a.right - base.left; const y1 = a.top + a.height / 2 - base.top;
      const x2 = b.left - base.left; const y2 = b.top + b.height / 2 - base.top;
      const mx = (x1 + x2) / 2;
      const rel = row.classList.contains('rel');
      const stroke = benchmark ? (rel ? 'var(--good)' : '#9a9ea8') : 'var(--accent)';
      paths += `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" stroke="${stroke}" class="${rel ? 'rel' : ''}" data-path="${esc(row.dataset.path)}"/>`;
    });
  }
  svg.innerHTML = paths;
}

/* ---------------- index lab ---------------- */
async function loadLab() {
  if (!state.configs) state.configs = await api('/api/configs');
  renderCodecs();
  renderMatrix();
  if (!$('#inspector-body').innerHTML) inspect($('#inspector-input').value);
}

function renderCodecs() {
  const row = state.configs.filter((c) => c.indexer === 'spimi' && c.dictionary === 'patricia' && c.built);
  const base = (row.find((c) => c.compression === 'standard') || {}).sizes;
  $('#codec-grid').innerHTML = ['standard', 'vbe', 'elias'].map((codec, i) => {
    const c = row.find((x) => x.compression === codec);
    const info = CODEC_INFO[codec];
    if (!c) return `<div class="card codec"><div class="name">${info.name}</div><div class="how">Not built yet.</div></div>`;
    const ratio = base ? c.sizes.postings / base.postings : 1;
    return `<div class="card codec">
      <div class="name"><span class="swatch" style="background:${info.color};display:inline-block;margin-right:8px"></span>${info.name}</div>
      <div class="how">${info.how}</div>
      <div class="size num">${kib(c.sizes.postings)}<small> KiB</small></div>
      <div class="ratio">${codec === 'standard' ? 'baseline' : `<b>${fmt((1 - ratio) * 100, 1)}%</b> smaller · ${fmt(1 / ratio, 2)}× compression`}</div>
      <div class="meter"><i style="width:${ratio * 100}%;background:${info.color};animation-delay:${i * 120}ms"></i></div>
    </div>`;
  }).join('');
}

function colorBits(codec, code) {
  if (codec === 'standard') {
    return code.split(' ').map((byte) => `<span class="${byte === '00000000' ? 'zero' : ''}">${byte}</span>`).join(' ');
  }
  if (codec === 'vbe') {
    return code.split(' ').map((byte) => `<span class="cont">${byte[0]}</span>${byte.slice(1)}`).join(' ');
  }
  const k = code.indexOf('1');
  return `<span class="unary">${code.slice(0, k)}</span><span class="sep">1</span><span class="rem">${code.slice(k + 1)}</span>`;
}

async function inspect(term) {
  const body = $('#inspector-body');
  body.innerHTML = '<div class="loading-note"><span class="spinner"></span>Reading postings…</div>';
  try {
    const p = await api(`/api/postings?${new URLSearchParams({ term, config: state.config })}`);
    const facts = [
      ['Stem', p.stem], ['Term ID', p.term_id], ['Document freq.', fmt(p.df)], ['Collection freq.', fmt(p.cf)],
      ['WAND upper bound', p.wand_upper_bound != null ? fmt(p.wand_upper_bound, 3) : '—'],
    ].map(([k, v]) => `<div class="fact"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>`).join('');
    const rows = p.doc_ids.map((d, i) => `<tr>
      <td class="num muted">${i + 1}</td><td class="mono">${d}</td><td class="mono">${i === 0 ? '—' : `+${p.gaps[i]}`}</td><td class="mono">${p.tfs[i]}</td>
      <td class="bits">${colorBits('standard', p.codecs.standard.codes[i])}</td>
      <td class="bits">${colorBits('vbe', p.codecs.vbe.codes[i])}</td>
      <td class="bits">${colorBits('elias', p.codecs.elias.codes[i])}</td></tr>`).join('');
    const max = Math.max(...Object.values(p.codecs).map((c) => c.bytes));
    const bars = ['standard', 'vbe', 'elias'].map((codec) => {
      const c = p.codecs[codec];
      return `<div class="bytes-row"><span>${CODEC_INFO[codec].name}</span>
        <div class="bar"><i style="width:${(c.bytes / max) * 100}%;background:${CODEC_INFO[codec].color}"></i></div>
        <span class="mono num" style="text-align:right">${fmt(c.bytes)} B</span></div>`;
    }).join('');
    body.innerHTML = `
      <div class="term-facts">${facts}</div>
      <div style="overflow-x:auto"><table class="ptable">
        <thead><tr><th>#</th><th>Doc ID</th><th>Gap</th><th>TF</th><th>Uncompressed (doc ID)</th><th>Variable-Byte (gap)</th><th>Elias-Gamma (gap + 1)</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <div class="bits-legend">
        <span><i style="background:var(--m-bm25)"></i>VByte continuation bit (1 = last byte)</span>
        <span><i style="background:var(--m-adaptive)"></i>Elias unary length</span>
        <span><i style="background:var(--ink)"></i>separator</span>
        <span><i style="background:var(--m-wand)"></i>binary offset</span>
      </div>
      <div style="margin-top:22px;font-size:13px;font-weight:600">Bytes on disk for this term (all ${fmt(p.df)} postings + term frequencies)</div>
      ${bars}`;
  } catch (e) {
    body.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function cellHtml(c) {
  const isDefault = c.key === state.overview.default_config;
  if (!c.built) {
    return `<div class="cell" data-key="${c.key}"><div class="muted" style="font-size:13px">Not built</div>
      <div class="foot"><span></span><button class="rebuild">Build</button></div><div class="progress"></div></div>`;
  }
  const s = c.sizes;
  return `<div class="cell ${isDefault ? 'default' : ''}" data-key="${c.key}">
    <div class="stats">
      <div>Postings<b class="num">${kib(s.postings)} KiB</b></div>
      <div>Dictionaries<b class="num">${kib(s.terms + s.docs)} KiB</b></div>
      <div>Index build<b class="num">${fmt(c.meta.index_seconds, 2)} s</b></div>
      <div>LSI build<b class="num">${c.meta.lsi_seconds != null ? `${fmt(c.meta.lsi_seconds, 2)} s` : '—'}</b></div>
    </div>
    <div class="foot"><span>${isDefault ? '<b style="color:var(--accent)">default</b> · ' : ''}${esc(c.meta.built_at.slice(11))}</span>
      <button class="rebuild">Rebuild</button></div>
    <div class="progress"></div></div>`;
}

function renderMatrix() {
  const head = `<div></div>` + ['standard', 'vbe', 'elias'].map((codec) =>
    `<div class="colh"><span class="swatch" style="background:${CODEC_INFO[codec].color};display:inline-block;margin-right:6px"></span>${CODEC_INFO[codec].name}</div>`).join('');
  const rows = ROWS.map(([indexer, dictionary]) => {
    const cells = ['standard', 'vbe', 'elias'].map((codec) =>
      cellHtml(state.configs.find((c) => c.key === `${indexer}-${dictionary}-${codec}`))).join('');
    const sample = state.configs.find((c) => c.indexer === indexer && c.dictionary === dictionary);
    return `<div class="rowh">${sample.labels[0]}<span>${sample.labels[1]} dictionary</span></div>${cells}`;
  }).join('');
  $('#matrix').innerHTML = head + rows;
}

async function rebuild(key) {
  const cell = $(`.cell[data-key="${key}"]`);
  cell.classList.remove('flash');
  cell.classList.add('building');
  cell.querySelector('.rebuild').disabled = true;
  cell.querySelector('.rebuild').textContent = 'Building…';
  try {
    const info = await api(`/api/configs/${key}/build`, { method: 'POST' });
    state.configs = state.configs.map((c) => (c.key === key ? info : c));
    cell.outerHTML = cellHtml(info);
    const fresh = $(`.cell[data-key="${key}"]`);
    fresh.classList.add('flash');
    renderCodecs();
  } catch (e) {
    cell.classList.remove('building');
    cell.querySelector('.rebuild').textContent = 'Failed';
  }
}

/* ---------------- evaluation ---------------- */
async function loadEvaluation() {
  if (state.evaluation) return;
  try {
    state.evaluation = await api('/api/evaluation');
    renderEvaluation(state.evaluation);
  } catch (e) {
    $('#evaluation-body').innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

function renderEvaluation(data) {
  const runs = data.runs;
  const best = runs[runs.length - 1];
  const baseline = runs[1];
  const metrics = [['ap', 'MAP'], ['ndcg', 'NDCG'], ['rbp', 'RBP'], ['dcg', 'DCG']];

  const kpis = metrics.map(([m, label]) => {
    const gain = (best.mean[m] / baseline.mean[m] - 1) * 100;
    return `<div class="card kpi"><div class="k"><span class="swatch" style="background:var(--m-adaptive)"></span>${label} · ${esc(best.label)}</div>
      <div class="v num">${fmt(best.mean[m], m === 'dcg' ? 2 : 3)}</div>
      <div class="d"><b>+${fmt(gain, 1)}%</b> vs ${esc(baseline.label)} (${fmt(baseline.mean[m], m === 'dcg' ? 2 : 3)})</div></div>`;
  }).join('');

  const legend = runs.map((r, i) => `<span><span class="swatch" style="background:${RUN_COLORS[i]}"></span>${esc(r.label)}</span>`).join('');

  $('#evaluation-body').innerHTML = `
    <div class="kpis">${kpis}</div>
    <div class="section">
      <div class="section-head"><div><h2>Mean scores by setup</h2><p>Higher is better. All metrics are averaged over the 30 queries.</p></div></div>
      <div class="card chart-card"><div class="legend">${legend}</div><div class="chart" id="grouped-chart"></div></div>
    </div>
    <div class="section">
      <div class="section-head"><div><h2>Leaderboard</h2><p>Time is the wall-clock for all 30 queries at depth 1000.</p></div></div>
      <div class="card" style="padding:8px 16px"><table class="leader" id="leader"></table></div>
    </div>
    <div class="section">
      <div class="section-head"><div><h2>Where the hybrid helps</h2><p id="per-query-summary"></p></div></div>
      <div class="card chart-card"><div class="chart" id="per-query-chart"></div></div>
    </div>`;

  renderGroupedChart(runs);
  renderLeaderboard(runs);
  renderPerQuery(data, best, baseline);
}

function renderGroupedChart(runs) {
  const metrics = [['rbp', 'RBP'], ['ndcg', 'NDCG'], ['ap', 'MAP']];
  const W = 1000; const H = 330; const top = 20; const bottom = 40; const left = 36;
  const plotH = H - top - bottom;
  const groupW = (W - left) / metrics.length;
  const barW = 34; const gap = 10;
  const y = (v) => top + plotH * (1 - v);
  let svg = '';
  [0, 0.25, 0.5, 0.75, 1].forEach((t) => {
    svg += `<line x1="${left}" x2="${W}" y1="${y(t)}" y2="${y(t)}" stroke="#ece9e1"/>
      <text x="${left - 8}" y="${y(t) + 4}" text-anchor="end" font-size="11" fill="#868a95">${t.toFixed(2)}</text>`;
  });
  metrics.forEach(([m, label], gi) => {
    const groupX = left + gi * groupW;
    const totalW = runs.length * barW + (runs.length - 1) * gap;
    const startX = groupX + (groupW - totalW) / 2;
    runs.forEach((r, ri) => {
      const v = r.mean[m];
      const x = startX + ri * (barW + gap);
      svg += `<rect class="bar" x="${x}" y="${y(v)}" width="${barW}" height="${plotH - (y(v) - top)}" rx="5" fill="${RUN_COLORS[ri]}" style="animation-delay:${gi * 120 + ri * 60}ms"/>
        <text x="${x + barW / 2}" y="${y(v) - 7}" text-anchor="middle" font-size="11" font-weight="600" fill="#464a55">${v.toFixed(3).replace(/^0/, '')}</text>`;
    });
    svg += `<text x="${groupX + groupW / 2}" y="${H - 12}" text-anchor="middle" font-size="14" font-weight="600" fill="#16181d">${label}</text>`;
  });
  $('#grouped-chart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Mean RBP, NDCG and MAP per retrieval setup">${svg}</svg>`;
}

function renderLeaderboard(runs) {
  const cols = [['rbp', 'RBP', 4], ['dcg', 'DCG', 3], ['ndcg', 'NDCG', 4], ['ap', 'MAP', 4]];
  const max = Object.fromEntries(cols.map(([m]) => [m, Math.max(...runs.map((r) => r.mean[m]))]));
  const bestAp = max.ap;
  const label = (key) => (state.configs || []).find((c) => c.key === key);
  $('#leader').innerHTML = `<thead><tr><th>Setup</th><th>Index</th>${cols.map(([, l]) => `<th>${l}</th>`).join('')}<th>Time</th></tr></thead>
    <tbody>${runs.map((r, i) => `<tr class="${r.mean.ap === bestAp ? 'best' : ''}">
      <td><span class="swatch" style="background:${RUN_COLORS[i]};display:inline-block;margin-right:10px"></span>${esc(r.label)}</td>
      <td style="font-family:var(--sans);font-size:12px;color:var(--muted)">${esc(label(r.config) ? configLabel(label(r.config)) : r.config)}</td>
      ${cols.map(([m, , d]) => `<td>${r.mean[m].toFixed(d)}<div class="cellbar"><i style="width:${(r.mean[m] / max[m]) * 100}%;background:${RUN_COLORS[i]}"></i></div></td>`).join('')}
      <td>${fmt(r.seconds, 2)} s</td></tr>`).join('')}</tbody>`;
}

function renderPerQuery(data, best, baseline) {
  const items = data.queries.map((q) => ({
    ...q, a: best.per_query[q.id].ap, b: baseline.per_query[q.id].ap,
  })).map((q) => ({ ...q, d: q.a - q.b })).sort((x, y) => y.d - x.d);
  const wins = items.filter((q) => q.d > 0.005).length;
  const losses = items.filter((q) => q.d < -0.005).length;
  $('#per-query-summary').innerHTML = `Average precision of <b>${esc(best.label)}</b> minus <b>${esc(baseline.label)}</b>, per query. Better on <b>${wins}</b>, worse on <b>${losses}</b>, tied on ${items.length - wins - losses}. Click a bar to compare that query.`;

  const W = 1000; const H = 280; const left = 36; const top = 16; const bottom = 34;
  const step = 0.1;
  const posExt = Math.max(step, Math.ceil(Math.max(...items.map((q) => q.d)) / step) * step);
  const negExt = Math.max(step, Math.ceil(-Math.min(...items.map((q) => q.d)) / step) * step);
  const scale = (H - top - bottom) / (posExt + negExt);
  const mid = top + posExt * scale;
  const slot = (W - left) / items.length;
  const bw = slot * 0.62;
  let svg = '';
  const ticks = [];
  for (let t = -negExt; t <= posExt + 1e-9; t += step) ticks.push(Math.round(t * 10) / 10);
  ticks.forEach((t) => {
    const yy = mid - t * scale;
    svg += `<line x1="${left}" x2="${W}" y1="${yy}" y2="${yy}" stroke="${t === 0 ? '#c9c6be' : '#f0eee8'}"/>
      <text x="${left - 8}" y="${yy + 4}" text-anchor="end" font-size="11" fill="#868a95">${t > 0 ? '+' : ''}${t.toFixed(1)}</text>`;
  });
  items.forEach((q, i) => {
    const x = left + i * slot + (slot - bw) / 2;
    const h = Math.max(Math.abs(q.d) * scale, 1.5);
    const yy = q.d >= 0 ? mid - h : mid;
    const color = q.d >= 0 ? 'var(--m-adaptive)' : 'var(--m-bm25)';
    svg += `<g class="qbar" data-id="${q.id}">
      <rect class="hit" x="${left + i * slot}" y="${top}" width="${slot}" height="${H - top - bottom}" fill="transparent"/>
      <rect class="bar" x="${x}" y="${yy}" width="${bw}" height="${h}" rx="3" fill="${color}" style="transform-origin:${q.d >= 0 ? 'bottom' : 'top'};animation-delay:${i * 20}ms"/>
      <text x="${x + bw / 2}" y="${H - 12}" text-anchor="middle" font-size="10" fill="#868a95">${q.id.slice(1)}</text></g>`;
  });
  const chart = $('#per-query-chart');
  chart.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Per-query average precision difference">${svg}</svg>`;
  chart.querySelectorAll('.qbar').forEach((g) => {
    const q = items.find((x) => x.id === g.dataset.id);
    g.addEventListener('mousemove', (e) => showTip(
      `<b>${q.id}</b> · ${esc(q.text.length > 140 ? `${q.text.slice(0, 140)}…` : q.text)}<br>
       <span class="muted">${esc(best.label)}</span> ${q.a.toFixed(3)} · <span class="muted">${esc(baseline.label)}</span> ${q.b.toFixed(3)}
       · <b>${q.d >= 0 ? '+' : ''}${q.d.toFixed(3)}</b>`, e));
    g.addEventListener('mouseleave', hideTip);
    g.addEventListener('click', () => { hideTip(); setHash('compare', { q: q.text }); });
  });
}

/* ---------------- boot ---------------- */
function bindEvents() {
  $('#search-form').addEventListener('submit', (e) => { e.preventDefault(); submitSearch($('#search-input').value); });
  $('#method-switch').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    state.method = btn.dataset.method;
    submitSearch($('#search-input').value);
  });
  $('#search-config').addEventListener('change', (e) => { state.config = e.target.value; submitSearch($('#search-input').value); });
  $('#results').addEventListener('click', (e) => {
    const card = e.target.closest('.result');
    if (card) openDoc(card.dataset.path, $('#search-input').value);
  });
  $('#suggestion-chips').addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (chip) submitSearch(queryText(chip.dataset.id));
  });

  $('#compare-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const q = $('#compare-input').value.trim();
    if (q) setHash('compare', { q, c: $('#compare-config').value });
  });
  $('#compare-config').addEventListener('change', () => {
    setHash('compare', { q: $('#compare-input').value.trim(), c: $('#compare-config').value });
  });

  $('#inspector-form').addEventListener('submit', (e) => { e.preventDefault(); inspect($('#inspector-input').value); });
  $('#matrix').addEventListener('click', (e) => {
    const btn = e.target.closest('.rebuild');
    if (btn) rebuild(btn.closest('.cell').dataset.key);
  });
  $('#rebuild-all').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    for (const c of state.configs) await rebuild(c.key); // eslint-disable-line no-await-in-loop
    btn.disabled = false;
    $('#inspector-body').innerHTML = '';
    inspect($('#inspector-input').value);
  });

  $('#drawer-close').addEventListener('click', closeDoc);
  $('#scrim').addEventListener('click', closeDoc);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDoc();
    if (e.key === '/' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
      const input = $('.view.active input[type="search"]');
      if (input) { e.preventDefault(); input.focus(); input.select(); }
    }
  });
  window.addEventListener('scroll', () => $('#topbar').classList.toggle('scrolled', window.scrollY > 4), { passive: true });
  window.addEventListener('resize', () => requestAnimationFrame(drawLinks));
  window.addEventListener('hashchange', route);
}

async function boot() {
  bindEvents();
  [state.overview, state.configs] = await Promise.all([api('/api/overview'), api('/api/configs')]);
  state.config = state.overview.default_config;
  const o = state.overview;
  $('#corpus-label').textContent = `MEDLINE · ${fmt(o.documents)} abstracts`;
  $('#hero-stats').innerHTML = `
    <span><b>${fmt(o.documents)}</b> documents</span><span><b>${fmt(o.terms)}</b> terms</span>
    <span><b>${o.configs}</b> index builds</span><span><b>${Object.keys(o.methods).length}</b> ranking models</span>`;
  $('#suggestion-chips').innerHTML = SUGGESTED.map((id) => {
    const text = queryText(id).replace(/\.$/, '');
    return `<button class="chip" type="button" data-id="${id}"><b>${id}</b>${esc(text.length > 54 ? `${text.slice(0, 54)}…` : text)}</button>`;
  }).join('');
  route();
}

boot();
