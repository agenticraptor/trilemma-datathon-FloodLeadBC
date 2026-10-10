/* FloodLead BC static app. Vanilla ES2020, no build step, no third-party requests.
 * Served under Content-Security-Policy: default-src 'self' — so no inline scripts/styles, no eval.
 * Data: same-origin API under /v1/...; if it cannot be reached, prepared snapshot files in
 * data/snapshot/<slug>.json are used instead (see web/README.md and snapshotSlug below). */
'use strict';

(function () {
  // ---------------------------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------------------------
  const API_TIMEOUT_MS = 12000;
  const TZ = 'America/Vancouver';
  const M_PER_FT = 0.3048;
  const CEDARVILLE = 'usgs:12210700';
  const OVERFLOW = 'usgs:12211195';
  const NOAA_LID = 'NRKW1';
  const STAGE_KEYS = ['action', 'minor', 'moderate', 'major'];
  const STAGE_NAMES = { action: 'Action', minor: 'Minor flood', moderate: 'Moderate flood', major: 'Major flood' };
  const COLORS = {
    obs: '#18222d', noaa: '#1f5fbf', fl: '#5d7f78', flEdge: 'rgba(93,127,120,0.55)', flBand: 'rgba(93,127,120,0.16)',
    personal: '#b0186b', ovf: '#0b7a8a', grid: '#e6e9ed', axis: '#56636f', now: '#8a96a3', marker: '#444444',
    action: '#c99a06', minor: '#e07b00', moderate: '#cc3311', major: '#7a2a8c',
  };
  const QUANTILES = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95];
  const TABLE_HORIZONS = [6, 12, 24, 48];
  const FL_LABEL = 'FloodLead baseline (persistence / trend), live skill being measured';
  const NOAA_LABEL = 'NOAA NWS official forecast (unmodified)';
  const PERSONAL_KEY = 'floodlead.personalLevelFt.v1';
  const MODEL_KEY = 'floodlead.model.v1';
  const DEFAULT_EVENTS = ['2021-11-14', '2025-12-10'];
  const FALLBACK_ATTRIBUTION = [
    'Contains information licensed under the Open Government Licence – Canada.',
    'Contains data from Environment and Climate Change Canada.',
    'Credit: U.S. Geological Survey.',
    'Official forecasts and flood categories: NOAA National Weather Service (not affiliated with or endorsed by NOAA/NWS).',
  ];
  const APP_VERSION = 'stage-03';
  const FEEDBACK_MAX = 1000;
  const FEEDBACK_OFFLINE = 'Feedback cannot be sent from the offline snapshot.';
  const GITHUB_FEEDBACK_URL = 'https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC/issues/new?template=feedback.yml';
  const REPO_URL = 'https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC';
  const TYPICAL_PEAK_LABEL = 'Typical yearly peak (reached in about half of years): FloodLead-derived from ECCC records, not an official flood level';
  const SOURCE_NAMES = { eccc: 'ECCC BC gauges', usgs: 'USGS Nooksack/Sumas gauges' };
  const STATION_ID_RE = /^[A-Za-z0-9:._-]{1,64}$/;

  // ---------------------------------------------------------------------------------------------
  // Snapshot file naming. The backend's `floodlead export-demo` must use the same rule.
  // tests/test_web.py parses the two regular expressions between the BEGIN/END markers.
  // ---------------------------------------------------------------------------------------------
  // BEGIN snapshotSlug
  function snapshotSlug(path) {
    return path.replace(/^\//, '').replace(/[^A-Za-z0-9._-]+/g, '_');
  }
  // END snapshotSlug

  // ---------------------------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------------------------
  const state = {
    apiDown: false,        // set after a network error or a non-JSON answer (e.g. a plain static server)
    snapshotTimes: [],     // snapshot_at / generated_at of every snapshot file used
    snapshotMissing: 0,    // snapshot files that were needed but not found
    attributionSet: false,
    charts: [],
    renderSeq: 0,
  };

  // ---------------------------------------------------------------------------------------------
  // Data access
  // ---------------------------------------------------------------------------------------------
  async function api(path) {
    if (!state.apiDown) {
      let res = null;
      const ctrl = typeof AbortController === 'function' ? new AbortController() : null;
      const timer = ctrl ? setTimeout(() => ctrl.abort(), API_TIMEOUT_MS) : null;
      try {
        res = await fetch(path, { headers: { Accept: 'application/json' }, cache: 'no-store', signal: ctrl ? ctrl.signal : undefined });
      } catch (e) {
        res = null;
      } finally {
        if (timer) clearTimeout(timer);
      }
      const isJson = !!res && (res.headers.get('content-type') || '').toLowerCase().includes('json');
      if (res && res.ok && isJson) {
        try {
          const body = await res.json();
          noteAttribution(body);
          return body;
        } catch (e) { /* malformed JSON: fall back to the snapshot below */ }
      } else if (res && res.status === 404 && isJson) {
        return null; // the live API answered: nothing here (or the endpoint is not deployed yet)
      }
      if (!res || !isJson) state.apiDown = true; // no API behind this origin (network error, timeout, static server)
    }
    return loadSnapshot(path);
  }

  async function loadSnapshot(path) {
    const url = 'data/snapshot/' + snapshotSlug(path) + '.json';
    try {
      const res = await fetch(url, { cache: 'no-cache' });
      if (!res.ok) throw new Error('missing');
      const body = await res.json();
      const at = body && (body.snapshot_at || body.generated_at);
      if (at) state.snapshotTimes.push(at);
      noteAttribution(body);
      updateBanner();
      return body;
    } catch (e) {
      state.snapshotMissing += 1;
      updateBanner();
      return null;
    }
  }

  /** In snapshot mode, the time of the (earliest) snapshot used; null when showing live data. */
  function snapshotRef() {
    if (!state.snapshotTimes.length) return null;
    const times = state.snapshotTimes.map(toDate).filter(Boolean).sort((a, b) => a - b);
    return times.length ? times[0] : null;
  }
  /** The snapshot time of a response body that came from a snapshot file (live API bodies have none). */
  function snapOf(body) { return body && typeof body.snapshot_at === 'string' ? body.snapshot_at : null; }
  /** The chart's "now" line: at the snapshot time when the charted data came from a snapshot. */
  function nowLine(ref) {
    const r = toDate(ref);
    return { t: (r ? r.getTime() : Date.now()) / 1000, color: COLORS.now, label: r ? 'snapshot' : 'now', dash: [2, 3], width: 1 };
  }

  function updateBanner() {
    const el = document.getElementById('snapshot-banner');
    if (!el) return;
    if (state.snapshotTimes.length) {
      const t = snapshotRef();
      el.textContent = t
        ? `Snapshot from ${fmtPacific(t)} (${fmtUtc(t)}) — live API not reachable`
        : 'Snapshot data — live API not reachable';
      el.hidden = false;
    } else if (state.apiDown) {
      el.textContent = 'Live API not reachable and no snapshot data found — numbers cannot be shown.';
      el.hidden = false;
    }
  }

  function noteAttribution(body) {
    if (state.attributionSet || !body || !Array.isArray(body.attribution) || !body.attribution.length) return;
    const ul = document.getElementById('attribution');
    if (!ul) return;
    clear(ul);
    for (const line of body.attribution) ul.appendChild(h('li', null, String(line)));
    state.attributionSet = true;
  }

  // ---------------------------------------------------------------------------------------------
  // DOM helpers (textContent only, never HTML strings; no style attributes)
  // ---------------------------------------------------------------------------------------------
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k === 'text') el.textContent = v;
        else if (k === 'dataset') Object.assign(el.dataset, v);
        else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
        else if (v === true) el.setAttribute(k, '');
        else el.setAttribute(k, String(v));
      }
    }
    appendKids(el, kids);
    return el;
  }
  function appendKids(el, ...kids) {
    const list = kids.flat(Infinity);
    for (const k of list) {
      if (k == null || k === false) continue;
      el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
    }
    return el;
  }
  function clear(el) { while (el && el.firstChild) el.removeChild(el.firstChild); return el; }
  function fill(el, ...kids) { clear(el); return appendKids(el, kids); }
  function placeholder(text) { return h('p', { class: 'placeholder' }, text); }
  function card(title, sub) {
    const body = h('div', { class: 'card-body' }, h('p', { class: 'loading' }, 'Loading…'));
    const el = h('section', { class: 'card' }, title ? h('h2', null, title) : null, sub ? h('p', { class: 'card-sub' }, sub) : null, body);
    el.body = body;
    return el;
  }
  /** A table in a horizontal scroll box. When it is wider than the box, a right-edge fade and a
   *  "scroll →" hint appear (toggled by a ResizeObserver and the scroll position). */
  const scrollObserver = typeof ResizeObserver === 'function'
    ? new ResizeObserver((entries) => { for (const e of entries) updateScrollCue(e.target.closest('.table-scroll')); })
    : null;
  function updateScrollCue(box) {
    if (!box) return;
    const wrap = box.querySelector('.table-wrap');
    if (!wrap) return;
    const over = wrap.scrollWidth > wrap.clientWidth + 1;
    box.classList.toggle('has-overflow', over);
    box.classList.toggle('at-end', !over || wrap.scrollLeft + wrap.clientWidth >= wrap.scrollWidth - 2);
  }
  function tableBox(table) {
    const wrap = h('div', { class: 'table-wrap' }, table);
    const box = h('div', { class: 'table-scroll' }, h('p', { class: 'scroll-hint', 'aria-hidden': 'true' }, 'scroll →'), wrap);
    wrap.addEventListener('scroll', () => updateScrollCue(box), { passive: true });
    if (scrollObserver) { scrollObserver.observe(wrap); scrollObserver.observe(table); }
    return box;
  }
  function extLink(href, text) { return h('a', { href, rel: 'noopener' }, text); }
  function isStale(seq) { return seq !== state.renderSeq; }

  async function section(el, seq, fn) {
    try {
      await fn();
    } catch (err) {
      console.error(err);
      if (!isStale(seq)) fill(el.body || el, h('p', { class: 'placeholder error' }, 'This section could not be displayed. The rest of the page still works.'));
    }
  }

  // ---------------------------------------------------------------------------------------------
  // Numbers, units, times
  // ---------------------------------------------------------------------------------------------
  const isNum = (v) => typeof v === 'number' && isFinite(v);
  const mToFt = (m) => m / M_PER_FT;
  const ftToM = (ft) => ft * M_PER_FT;
  function fmt(v, d) { return isNum(v) ? v.toFixed(d) : '—'; }
  function toDate(s) {
    if (!s) return null;
    const d = s instanceof Date ? s : new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }
  const tSec = (d) => d.getTime() / 1000;
  const dtfPacific = new Intl.DateTimeFormat('en-US', { timeZone: TZ, weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short' });
  const dtfPacificYear = new Intl.DateTimeFormat('en-US', { timeZone: TZ, year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short' });
  const dtfPacificShort = new Intl.DateTimeFormat('en-US', { timeZone: TZ, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const dtfUtc = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const dtfDate = new Intl.DateTimeFormat('en-US', { timeZone: TZ, year: 'numeric', month: 'short', day: 'numeric' });
  const dtfAxisDay = new Intl.DateTimeFormat('en-US', { timeZone: TZ, month: 'short', day: 'numeric' });
  const dtfAxisHm = new Intl.DateTimeFormat('en-US', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const dtfLegend = new Intl.DateTimeFormat('en-US', { timeZone: TZ, weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  function fmtPacific(d) { d = toDate(d); return d ? dtfPacific.format(d) : '—'; }
  function fmtPacificYear(d) { d = toDate(d); return d ? dtfPacificYear.format(d) : '—'; }
  function fmtPacificShort(d) { d = toDate(d); return d ? dtfPacificShort.format(d) : '—'; }
  function fmtUtc(d) { d = toDate(d); return d ? dtfUtc.format(d) + ' UTC' : '—'; }
  function fmtDate(d) { d = toDate(d); return d ? dtfDate.format(d) : '—'; }
  function fmtDuration(minutes) {
    if (!isNum(minutes)) return '—';
    const m = Math.round(Math.abs(minutes));
    const hh = Math.floor(m / 60);
    const mm = m % 60;
    if (hh === 0) return `${mm} min`;
    if (hh >= 72) return `${Math.round(hh / 24)} days`;
    return `${hh} h ${mm} min`;
  }
  /** Age of a data time. `snapRef` (the snapshot_at of the body the time came from) makes it relative
   *  to the snapshot time, not the viewer's clock. */
  function ageText(d, snapRef) {
    d = toDate(d);
    if (!d) return '';
    const ref = toDate(snapRef);
    if (ref) {
      // Snapshot mode: ages relative to the snapshot time, not the viewer's clock.
      const sm = (ref.getTime() - d.getTime()) / 60000;
      if (sm < -5) return `${fmtDuration(-sm)} after the snapshot`;
      if (sm < 1) return 'at snapshot time';
      if (sm < 180) return `${Math.round(sm)} min before the snapshot`;
      return `${fmtDuration(sm)} before the snapshot`;
    }
    const min = (Date.now() - d.getTime()) / 60000;
    if (min < -1) return `${fmtDuration(-min)} ahead`;
    if (min < 1) return 'just now';
    if (min < 180) return `${Math.round(min)} min ago`;
    return `${fmtDuration(min)} ago`;
  }
  function ageSpan(iso, snapRef) {
    const d = toDate(iso);
    if (!d) return null;
    const ref = toDate(snapRef);
    return h('span', { class: 'age', dataset: ref ? { ts: d.toISOString(), snap: ref.toISOString() } : { ts: d.toISOString() } }, ageText(d, ref));
  }
  function updateAges() {
    for (const el of document.querySelectorAll('.age[data-ts]')) el.textContent = ageText(el.dataset.ts, el.dataset.snap);
  }
  /** "Thu, Oct 8, 12:15 PDT · Oct 8, 19:15 UTC · 33 min ago" */
  function timeLine(iso, withUtc, snapRef) {
    const d = toDate(iso);
    if (!d) return h('span', { class: 'muted' }, 'time unknown');
    return h('span', null, fmtPacific(d), withUtc === false ? null : ` · ${fmtUtc(d)}`, ' · ', ageSpan(d, snapRef));
  }
  function fmtPct(p) {
    if (!isNum(p)) return '—';
    if (p < 0.005) return '< 1 %';
    if (p > 0.995) return '> 99 %';
    return `${Math.round(p * 100)} %`;
  }
  function pClass(p) { return isNum(p) ? (p >= 0.5 ? 'p hi' : p >= 0.1 ? 'p mid' : 'p') : 'p'; }
  const nfInt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
  function fmtInt(v) { return isNum(v) ? nfInt.format(v) : '—'; }
  /** Skill score as a signed percent: 0.203 -> "+20.3 %", -0.022 -> "−2.2 %" (U+2212 minus). */
  function fmtSkill(v) {
    if (!isNum(v)) return '—';
    const r = Math.round(v * 1000) / 10;
    if (r === 0) return '0.0 %';
    return `${r > 0 ? '+' : '−'}${Math.abs(r).toFixed(1)} %`;
  }
  function stationHref(id) { return `#/station/${encodeURIComponent(id).replace(/%3A/gi, ':')}`; }
  function shortHash(hx) { return typeof hx === 'string' && hx.length > 16 ? `${hx.slice(0, 10)}…${hx.slice(-6)}` : (hx || '—'); }
  const SMALL_WORDS = new Set(['at', 'of', 'the', 'near', 'above', 'below', 'and', 'in', 'on', 'to']);
  const UPPER_WORDS = new Set(['WA', 'BC', 'USA', 'SR', 'NF', 'MF', 'SF', 'II', 'D/S', 'U/S']);
  function titleCase(s) {
    if (!s || /[a-z]/.test(s)) return s || '';
    return s.split(/\s+/).map((w, i) => {
      const bare = w.replace(/[,.()]/g, '');
      if (UPPER_WORDS.has(bare)) return w;
      const lw = w.toLowerCase();
      if (i > 0 && SMALL_WORDS.has(lw)) return lw;
      return lw.replace(/(^|[-(/'])([a-z])/g, (m, a, b) => a + b.toUpperCase());
    }).join(' ');
  }
  function isUsStation(st) { return !!st && (st.source === 'usgs' || st.region === 'WA'); }
  function stationCategories(st) {
    const ot = st && st.official_thresholds;
    const cats = ot && ot.categories ? ot.categories : {};
    return STAGE_KEYS.filter((k) => cats[k] && (isNum(cats[k].stage_ft) || isNum(cats[k].stage_m))).map((k) => {
      const c = cats[k];
      const ft = isNum(c.stage_ft) ? c.stage_ft : mToFt(c.stage_m);
      const m = isNum(c.stage_m) ? c.stage_m : ftToM(c.stage_ft);
      return { key: k, name: STAGE_NAMES[k], ft, m, color: COLORS[k] };
    });
  }
  function modelName(id) {
    if (!id) return 'model';
    if (id === 'persistence-v1') return 'Persistence + typical drift (persistence-v1)';
    if (id === 'trend3h-v1') return 'Trend over 3 h, held after 6 h (trend3h-v1)';
    if (id.startsWith('persistence')) return `Persistence + typical drift (${id})`;
    if (id.startsWith('trend')) return `Trend (${id})`;
    return id;
  }
  const MODEL_EXPLAIN = "persistence-v1: the current level plus the station's typical past change over the same lead time (from its own history). trend3h-v1: the last 3 h trend, applied for at most 6 h.";
  function qmap(obj) {
    const out = new Map();
    if (!obj) return out;
    for (const [k, v] of Object.entries(obj)) {
      const p = parseFloat(k);
      if (isFinite(p) && isNum(v)) out.set(Math.round(p * 1000) / 1000, v);
    }
    return out;
  }

  /**
   * P(max level over the window >= levelM), by linear interpolation of the CDF through the
   * seven qmax quantile points. Returns {p, text}; below the 0.05 quantile -> ">= 95 %",
   * above the 0.95 quantile -> "< 5 %".
   */
  function pExceedFromQuantiles(qobj, levelM) {
    const m = qmap(qobj);
    const qs = [];
    for (const p of QUANTILES) {
      if (!m.has(p)) return { p: null, text: '—' };
      qs.push(m.get(p));
    }
    for (let i = 1; i < qs.length; i++) qs[i] = Math.max(qs[i], qs[i - 1]); // enforce monotone
    if (levelM < qs[0]) return { p: 0.95, text: '≥ 95 %', bound: 'ge' };
    if (levelM > qs[qs.length - 1]) return { p: 0.0, text: '< 5 %', bound: 'lt' };
    let cdf = QUANTILES[QUANTILES.length - 1];
    for (let i = 0; i < qs.length - 1; i++) {
      if (levelM <= qs[i + 1]) {
        const span = qs[i + 1] - qs[i];
        cdf = span > 0 ? QUANTILES[i] + (QUANTILES[i + 1] - QUANTILES[i]) * (levelM - qs[i]) / span : QUANTILES[i];
        break;
      }
    }
    const p = 1 - cdf;
    return { p, text: `${Math.round(p * 100)} %` };
  }

  // ---------------------------------------------------------------------------------------------
  // Local preferences (personal level never leaves the device)
  // ---------------------------------------------------------------------------------------------
  function loadPref(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } }
  function savePref(key, v) {
    try {
      if (v == null) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, String(v));
    } catch (e) { /* storage disabled: keep in memory only */ }
  }
  function loadPersonal() { const n = parseFloat(loadPref(PERSONAL_KEY)); return isFinite(n) ? n : null; }

  // ---------------------------------------------------------------------------------------------
  // Charts (uPlot)
  // ---------------------------------------------------------------------------------------------
  function destroyCharts() {
    for (const u of state.charts) { try { u.destroy(); } catch (e) { /* ignore */ } }
    state.charts = [];
  }
  function removeChart(u) {
    if (!u) return;
    state.charts = state.charts.filter((c) => c !== u);
    try { u.destroy(); } catch (e) { /* ignore */ }
  }
  function chartSize(container) {
    const w = Math.max(260, Math.floor(container.clientWidth || (container.parentElement && container.parentElement.clientWidth) || 600));
    return { width: w, height: w < 520 ? 250 : 330 };
  }
  /** x-axis tick labels (Pacific time, explicit 'en-US' formatter; never navigator.language). */
  function timeAxisValues(u, splits, axisIdx, foundSpace, foundIncr) {
    let prevDay = null;
    return splits.map((ts) => {
      if (!isNum(ts)) return '';
      const d = new Date(ts * 1000);
      const day = dtfAxisDay.format(d);
      if (isNum(foundIncr) && foundIncr >= 86400) return day;
      const label = day !== prevDay ? `${dtfAxisHm.format(d)}\n${day}` : dtfAxisHm.format(d);
      prevDay = day;
      return label;
    });
  }
  const X_SERIES = { label: 'Time (Pacific)', value: (u, ts) => (isNum(ts) ? dtfLegend.format(new Date(ts * 1000)) : '—') };
  const X_AXIS = { stroke: COLORS.axis, grid: { stroke: COLORS.grid, width: 1 }, ticks: { stroke: COLORS.grid, width: 1 }, values: timeAxisValues };

  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      for (const u of state.charts) {
        const c = u.root && u.root.parentElement;
        if (c && c.clientWidth) u.setSize(chartSize(c));
      }
    }, 150);
  });

  /** Align several [[tSec, v], ...] lists on one x array. Absent points are `undefined` (spanned);
   *  explicit nulls (inserted for real data gaps) break the line. */
  function alignSeries(list) {
    const xs = new Set();
    for (const s of list) if (s) for (const p of s) xs.add(p[0]);
    const x = Array.from(xs).sort((a, b) => a - b);
    const idx = new Map(x.map((t, i) => [t, i]));
    const out = [x];
    for (const s of list) {
      const arr = new Array(x.length).fill(undefined);
      if (s) for (const [t, v] of s) arr[idx.get(t)] = v;
      out.push(arr);
    }
    return out;
  }
  /** Insert a null between observations more than maxGapSec apart so the chart shows the gap. */
  function withGaps(points, maxGapSec) {
    const out = [];
    for (let i = 0; i < points.length; i++) {
      if (i > 0 && points[i][0] - points[i - 1][0] > maxGapSec) out.push([Math.round((points[i][0] + points[i - 1][0]) / 2), null]);
      out.push(points[i]);
    }
    return out;
  }

  function drawOverlays(u, ov) {
    const ctx = u.ctx;
    const dpr = (window.uPlot && uPlot.pxRatio) || window.devicePixelRatio || 1;
    const { left, top, width, height } = u.bbox;
    ctx.save();
    ctx.beginPath();
    ctx.rect(left, top, width, height);
    ctx.clip();
    ctx.font = `${Math.round(11 * dpr)}px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`;
    for (const ln of ov.hlines()) {
      if (!isNum(ln.value)) continue;
      const y = Math.round(u.valToPos(ln.value, ln.scale || 'y', true));
      if (y < top - 1 || y > top + height + 1) continue;
      ctx.strokeStyle = ln.color;
      ctx.lineWidth = (ln.width || 1.5) * dpr;
      ctx.setLineDash((ln.dash || [6, 4]).map((d) => d * dpr));
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(left + width, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = ln.color;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillText(ln.label, left + 4 * dpr, y - 2 * dpr);
    }
    for (const vl of ov.vlines()) {
      if (!isNum(vl.t)) continue;
      const x = Math.round(u.valToPos(vl.t, 'x', true));
      if (x < left - 1 || x > left + width + 1) continue;
      ctx.strokeStyle = vl.color;
      ctx.lineWidth = (vl.width || 1.5) * dpr;
      ctx.setLineDash((vl.dash || [3, 3]).map((d) => d * dpr));
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, top + height);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = vl.color;
      const rightHalf = x > left + width * 0.6;
      ctx.textAlign = rightHalf ? 'right' : 'left';
      ctx.textBaseline = 'top';
      ctx.fillText(vl.label, x + (rightHalf ? -4 : 4) * dpr, top + (vl.row || 0) * 14 * dpr + 4 * dpr);
    }
    ctx.restore();
  }

  /**
   * Level chart: observed + optional NOAA forecast + optional FloodLead median/band, stage lines.
   * spec: {unit:'ft'|'m', mAxis:boolean, obs:[[t,v]], noaa:{points:[[t,v]], label}|null,
   *        fl:{median, lo, hi}|null, hlines:()=>[...], vlines:()=>[...]}
   */
  function levelChart(container, spec) {
    if (typeof window.uPlot !== 'function') {
      fill(container, placeholder('The chart library did not load; the numbers above are still current.'));
      return null;
    }
    const unit = spec.unit;
    const dec = unit === 'ft' ? 2 : (spec.mDecimals || 2);
    const fmtV = (v) => (isNum(v) ? `${v.toFixed(dec)} ${unit}` : '—');
    const lists = [spec.obs];
    const series = [
      Object.assign({}, X_SERIES),
      { label: 'Observed (provisional)', stroke: COLORS.obs, width: 2, points: { show: false }, value: (u, v) => fmtV(v) },
    ];
    if (spec.noaa && spec.noaa.points && spec.noaa.points.length) {
      lists.push(spec.noaa.points);
      series.push({ label: spec.noaa.label || NOAA_LABEL, stroke: COLORS.noaa, width: 2, dash: [7, 4], spanGaps: true, points: { show: true, size: 6, stroke: COLORS.noaa, fill: '#ffffff', width: 2 }, value: (u, v) => fmtV(v) });
    }
    let bands;
    if (spec.fl) {
      const hiIdx = series.length;
      lists.push(spec.fl.hi, spec.fl.lo, spec.fl.median);
      series.push(
        { label: 'FloodLead 90 %', stroke: COLORS.flEdge, width: 1, spanGaps: true, points: { show: false }, value: (u, v) => fmtV(v) },
        { label: 'FloodLead 10 %', stroke: COLORS.flEdge, width: 1, spanGaps: true, points: { show: false }, value: (u, v) => fmtV(v) },
        { label: 'FloodLead median', stroke: COLORS.fl, width: 2, dash: [2, 3], spanGaps: true, points: { show: false }, value: (u, v) => fmtV(v) },
      );
      bands = [{ series: [hiIdx, hiIdx + 1], fill: COLORS.flBand }];
    }
    const data = alignSeries(lists);
    if (!data[0].length) {
      fill(container, placeholder('No data to chart.'));
      return null;
    }
    // y-range covers the data, the stage lines and the personal level
    let lo = Infinity;
    let hi = -Infinity;
    for (let i = 1; i < data.length; i++) for (const v of data[i]) if (isNum(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    const yRange = () => {
      let a = lo;
      let b = hi;
      for (const ln of spec.hlines()) if (isNum(ln.value) && (ln.scale || 'y') === 'y') { a = Math.min(a, ln.value); b = Math.max(b, ln.value); }
      if (!isFinite(a)) { a = 0; b = 1; }
      const pad = Math.max((b - a) * 0.06, unit === 'ft' ? 0.3 : 0.1);
      return [a - pad, b + pad];
    };
    const size = chartSize(container);
    const narrow = size.width < 480;
    const axes = [
      Object.assign({}, X_AXIS),
      { scale: 'y', label: narrow ? undefined : (unit === 'ft' ? 'Stage (ft)' : 'Level (m)'), stroke: COLORS.axis, size: narrow ? 46 : 58, grid: { stroke: COLORS.grid, width: 1 }, ticks: { stroke: COLORS.grid, width: 1 }, values: (u, splits) => splits.map((v) => (unit === 'ft' ? v.toFixed(1) : v.toFixed(2))) },
    ];
    if (spec.mAxis && !narrow) {
      axes.push({ scale: 'y', side: 1, label: 'Stage (m)', stroke: COLORS.axis, size: 54, grid: { show: false }, ticks: { show: false }, values: (u, splits) => splits.map((v) => ftToM(v).toFixed(2)) });
    }
    const opts = {
      width: size.width,
      height: size.height,
      tzDate: (ts) => uPlot.tzDate(new Date(ts * 1e3), TZ),
      scales: { x: { time: true }, y: { range: yRange } },
      axes,
      series,
      bands,
      legend: { live: true },
      cursor: { drag: { x: true, y: false } },
      hooks: { draw: [(u) => drawOverlays(u, spec)] },
    };
    clear(container);
    const u = new uPlot(opts, data, container);
    state.charts.push(u);
    return u;
  }

  function obsToPoints(observations, unit) {
    const pts = [];
    for (const o of observations || []) {
      if (!o || o.is_sentinel) continue;
      const d = toDate(o.ts);
      if (!d) continue;
      let v;
      if (unit === 'ft') v = o.raw_unit === 'ft' && isNum(o.raw_value) ? o.raw_value : (isNum(o.value) ? mToFt(o.value) : null);
      else v = isNum(o.value) ? o.value : null;
      if (v == null) continue;
      pts.push([tSec(d), v]);
    }
    pts.sort((a, b) => a[0] - b[0]);
    const dedup = [];
    for (const p of pts) if (!dedup.length || dedup[dedup.length - 1][0] !== p[0]) dedup.push(p);
    return withGaps(dedup, 2 * 3600);
  }
  function latestIssuance(off) {
    const iss = off && Array.isArray(off.issuances) ? off.issuances.filter((i) => i && Array.isArray(i.points) && i.points.length) : [];
    if (!iss.length) return null;
    return iss.slice().sort((a, b) => (toDate(b.issued_at) || 0) - (toDate(a.issued_at) || 0))[0];
  }
  function noaaPoints(issuance, unit) {
    if (!issuance) return null;
    const pts = [];
    for (const p of issuance.points || []) {
      const d = toDate(p.valid_at);
      if (!d || !isNum(p.stage_ft)) continue;
      pts.push([tSec(d), unit === 'ft' ? p.stage_ft : ftToM(p.stage_ft)]);
    }
    pts.sort((a, b) => a[0] - b[0]);
    return pts.length ? pts : null;
  }
  function flSeries(model, unit) {
    if (!model || !Array.isArray(model.horizons) || !model.horizons.length) return null;
    const conv = (m) => (unit === 'ft' ? mToFt(m) : m);
    const med = [];
    const lo = [];
    const hi = [];
    const d0 = toDate(model.data_as_of);
    if (d0 && isNum(model.level_at_data_as_of_m)) {
      const v = conv(model.level_at_data_as_of_m);
      med.push([tSec(d0), v]); lo.push([tSec(d0), v]); hi.push([tSec(d0), v]);
    }
    for (const hz of model.horizons.slice().sort((a, b) => a.h - b.h)) {
      const d = toDate(hz.valid_at);
      const q = qmap(hz.q);
      if (!d) continue;
      if (q.has(0.5)) med.push([tSec(d), conv(q.get(0.5))]);
      if (q.has(0.1)) lo.push([tSec(d), conv(q.get(0.1))]);
      if (q.has(0.9)) hi.push([tSec(d), conv(q.get(0.9))]);
    }
    return med.length > 1 ? { median: med, lo, hi } : null;
  }

  // ---------------------------------------------------------------------------------------------
  // Shared components
  // ---------------------------------------------------------------------------------------------
  function copyButton(text, label) {
    const btn = h('button', { type: 'button', class: 'small', 'aria-label': label || 'Copy full hash' }, 'copy');
    btn.addEventListener('click', () => {
      const done = (ok) => { btn.textContent = ok ? 'copied' : text; setTimeout(() => { btn.textContent = 'copy'; }, ok ? 1500 : 15000); };
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(() => done(true), () => done(false));
        else done(false);
      } catch (e) { done(false); }
    });
    return btn;
  }
  function hashView(hx) {
    if (!hx) return h('span', { class: 'muted' }, '—');
    return h('span', { class: 'hash' }, h('code', { title: hx }, shortHash(hx)), copyButton(hx));
  }
  function provisionalTag() { return h('span', { class: 'prov' }, 'provisional real-time data'); }

  function legendKey(items) {
    return h('ul', { class: 'legend-key' }, items.map((it) => h('li', null, h('span', { class: `swatch ${it.cls}` }), it.text)));
  }

  function modelTabs(models, selectedIdx, onPick) {
    if (models.length < 2) return null;
    return h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'FloodLead baseline model' },
      models.map((m, i) => h('button', { type: 'button', role: 'tab', 'aria-selected': i === selectedIdx ? 'true' : 'false', onclick: () => onPick(i) }, modelName(m.model))));
  }
  function pickModelIdx(models) {
    const want = loadPref(MODEL_KEY);
    const i = models.findIndex((m) => m.model === want);
    if (i >= 0) return i;
    const t = models.findIndex((m) => String(m.model || '').startsWith('trend'));
    return t >= 0 ? t : 0;
  }

  /** Chances table for one model: rows = thresholds, columns = within 6/12/24/48 h. */
  function chancesTable(model, us) {
    const thresholds = Array.isArray(model.thresholds) ? model.thresholds : [];
    const hz = TABLE_HORIZONS.map((hh) => (model.horizons || []).find((z) => z.h === hh) || null);
    if (!thresholds.length || hz.every((z) => !z)) return placeholder('This forecast has no thresholds or horizons to show.');
    const head = h('tr', null, h('th', null, 'Chance of reaching…'),
      TABLE_HORIZONS.map((hh, i) => h('th', { class: 'p' }, `within ${hh} h`, hz[i] ? h('small', { class: 'muted' }, h('br'), `by ${fmtPacificShort(hz[i].valid_at)}`) : null)));
    const rows = thresholds.map((t) => {
      let lvl = '';
      if (us && isNum(t.level_ft)) lvl = `${fmt(t.level_ft, 2)} ft (${fmt(t.level_m, 2)} m)`;
      else if (us && isNum(t.level_m)) lvl = `${fmt(mToFt(t.level_m), 2)} ft (${fmt(t.level_m, 2)} m)`;
      else if (isNum(t.level_m)) lvl = `${fmt(t.level_m, 2)} m`;
      const stageKey = String(t.key || '').startsWith('official:') ? String(t.key).slice(9) : null;
      return h('tr', null,
        h('td', { class: `row-label${stageKey ? ' stage-cell' : ''}` }, stageKey ? h('span', { class: `swatch sw-${stageKey}` }) : null, ' ', t.label || t.key, h('small', { class: 'muted' }, lvl)),
        hz.map((z) => {
          const p = z && z.p_exceed ? z.p_exceed[t.key] : null;
          return h('td', { class: pClass(p) }, fmtPct(p));
        }));
    });
    return tableBox(h('table', { class: 'chances' }, h('thead', null, head), h('tbody', null, rows)));
  }

  function forecastMeta(model, snapRef) {
    const base = toDate(model.base_time);
    const asOf = toDate(model.data_as_of);
    const created = toDate(model.created_at);
    // Input age = created_at - data_as_of (as recorded in the ledger entry).
    const inputAgeMin = isNum(model.input_age_min) ? model.input_age_min : (created && asOf ? (created - asOf) / 60000 : null);
    return h('div', null,
      h('dl', { class: 'kv' },
        h('dt', null, 'Base time'), h('dd', null, base ? timeLine(model.base_time, true, snapRef) : '—'),
        h('dt', null, 'Data as of'), h('dd', null, asOf ? timeLine(model.data_as_of, true, snapRef) : '—'),
        h('dt', null, 'Input age when issued'), h('dd', null, isNum(inputAgeMin) ? fmtDuration(inputAgeMin) : '—'),
        h('dt', null, 'Ledger entry'), h('dd', null, isNum(model.seq) ? `seq ${model.seq} · ` : '', hashView(model.entry_hash))),
      model.stale_inputs ? h('p', { class: 'notice' }, 'Stale inputs: the newest observation was too old when this forecast was made. Treat it with extra caution.') : null);
  }

  function chancesBlock(fc, us, onModelChange) {
    const wrap = h('div');
    const models = fc && Array.isArray(fc.models) ? fc.models.filter(Boolean) : [];
    if (!models.length) {
      fill(wrap, placeholder('No FloodLead forecast issued yet — hourly issuance starts soon.'));
      return wrap;
    }
    let idx = pickModelIdx(models);
    const render = () => {
      const m = models[idx];
      fill(wrap,
        h('p', null, h('span', { class: 'tag tag-fl' }, fc.label || FL_LABEL), ' ',
          h('a', { href: '/v1/scores/summary' }, 'Scores'), h('span', { class: 'muted' }, ' (live skill being measured)')),
        modelTabs(models, idx, (i) => { idx = i; savePref(MODEL_KEY, models[i].model); render(); if (onModelChange) onModelChange(models[i]); }),
        h('p', { class: 'model-explain' }, MODEL_EXPLAIN),
        chancesTable(m, us),
        h('p', { class: 'muted' }, 'Chance that the highest level between the data time and each horizon reaches the threshold, from the model’s simulated paths. These baselines are simple reference forecasts; their skill is being measured live.'),
        forecastMeta(m, snapOf(fc)));
    };
    render();
    wrap.selectedModel = () => models[idx];
    return wrap;
  }

  /** "Was this useful?" box, the last card on every page. The typed text is only read from the
   *  textarea and sent; it is never rendered anywhere. Server messages are shown as text only. */
  function feedbackBox(stationId) {
    let useful = null;
    let sending = false;
    const yes = h('button', { type: 'button', 'aria-pressed': 'false' }, 'Yes');
    const no = h('button', { type: 'button', 'aria-pressed': 'false' }, 'No');
    const text = h('textarea', { id: 'fb-text', rows: '3', maxlength: String(FEEDBACK_MAX), autocomplete: 'off', 'aria-describedby': 'fb-privacy fb-count' });
    const count = h('p', { id: 'fb-count', class: 'fb-count' });
    const send = h('button', { type: 'submit', class: 'primary' }, 'Send feedback');
    const status = h('p', { class: 'fb-status', role: 'status', 'aria-live': 'polite' });
    const sync = () => {
      yes.setAttribute('aria-pressed', useful === true ? 'true' : 'false');
      no.setAttribute('aria-pressed', useful === false ? 'true' : 'false');
      fill(count, `${fmtInt(text.value.length)} / ${fmtInt(FEEDBACK_MAX)} characters`);
      send.disabled = sending || (useful === null && !text.value.trim());
    };
    const setStatus = (msg, cls) => { status.className = `fb-status${cls ? ` ${cls}` : ''}`; fill(status, msg || ''); };
    yes.addEventListener('click', () => { useful = useful === true ? null : true; setStatus(''); sync(); });
    no.addEventListener('click', () => { useful = useful === false ? null : false; setStatus(''); sync(); });
    text.addEventListener('input', sync);
    const form = h('form', { class: 'feedback-form', novalidate: true },
      h('div', { class: 'tabs', role: 'group', 'aria-label': 'Was this page useful?' }, yes, no),
      h('label', { for: 'fb-text' }, 'Anything to add? (optional)'),
      h('p', { id: 'fb-privacy', class: 'fb-privacy' }, 'Please do not include your name, phone number, address or other personal information.'),
      text, count,
      h('div', { class: 'input-row' }, send, status));
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = { route: location.hash || '#/', station_id: stationId || null, useful, text: text.value.trim().slice(0, FEEDBACK_MAX), app_version: APP_VERSION };
      if (sending || (body.useful === null && !body.text)) return;
      sending = true;
      sync();
      setStatus('Sending…');
      let r;
      try { r = await postFeedback(body); } catch (err) { r = { ok: false, message: FEEDBACK_OFFLINE }; }
      sending = false;
      if (r.ok) { useful = null; text.value = ''; }
      setStatus(r.message, r.ok ? 'ok' : 'error');
      sync();
    });
    sync();
    return h('section', { class: 'card feedback' },
      h('h2', null, 'Was this useful?'),
      form,
      h('p', { class: 'fb-github' }, h('a', { href: GITHUB_FEEDBACK_URL, rel: 'noopener', target: '_blank' }, 'Prefer GitHub? Open an issue'),
        h('span', { class: 'muted' }, ' (GitHub issues are public; use it if you would like a reply)')));
  }

  /** POST /v1/feedback; returns {ok, message}. No request is made when this page is running on snapshot data. */
  async function postFeedback(payload) {
    if (state.apiDown) return { ok: false, message: FEEDBACK_OFFLINE };
    const ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = ctrl ? setTimeout(() => ctrl.abort(), API_TIMEOUT_MS) : null;
    let res;
    try {
      res = await fetch('/v1/feedback', {
        method: 'POST', cache: 'no-store', body: JSON.stringify(payload), signal: ctrl ? ctrl.signal : undefined,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      });
    } catch (e) {
      return { ok: false, message: FEEDBACK_OFFLINE };
    } finally {
      if (timer) clearTimeout(timer);
    }
    const isJson = (res.headers.get('content-type') || '').toLowerCase().includes('json');
    let body = null;
    if (isJson) { try { body = await res.json(); } catch (e) { body = null; } }
    if (res.status === 202 || (res.ok && body && body.status === 'received')) return { ok: true, message: 'Thank you. Your feedback was received.' };
    if (res.status === 429) return { ok: false, message: 'Too many submissions from this connection. Please try again later.' };
    if (res.status === 400 || res.status === 413 || res.status === 422) {
      return { ok: false, message: detailText(body) || (res.status === 413 ? 'Your feedback is too long.' : 'This feedback could not be accepted.') };
    }
    // A non-JSON answer other than a gateway error means there is no API behind this origin (a plain static server).
    if (!isJson && ![502, 503, 504].includes(res.status)) return { ok: false, message: FEEDBACK_OFFLINE };
    if (res.status === 404 || res.status === 405) return { ok: false, message: 'Feedback is not available on this server yet. Please open a GitHub issue instead.' };
    return { ok: false, message: `Feedback could not be sent right now (HTTP ${res.status}). Please try again later.` };
  }
  /** The `detail` of an error body as plain text (a string, or FastAPI's list of {msg}). */
  function detailText(body) {
    const d = body && body.detail;
    let s = '';
    if (typeof d === 'string') s = d;
    else if (Array.isArray(d)) s = d.map((x) => (x && typeof x.msg === 'string' ? x.msg : '')).filter(Boolean).join('; ');
    return s.length > 300 ? `${s.slice(0, 300)}…` : s;
  }

  // ---------------------------------------------------------------------------------------------
  // Screen 1: Sumas Prairie overflow watch
  // ---------------------------------------------------------------------------------------------
  function renderWatch(seq) {
    const main = document.getElementById('app');
    document.title = 'FloodLead BC: Sumas Prairie overflow watch';
    const w = { seq, personalFt: loadPersonal(), chart: null, fc: null, station: null, model: null, onPersonal: [] };

    const fraserCard = card('Fraser Valley gauges', null);
    fraserCard.id = 'fraser-valley';
    fraserCard.setAttribute('tabindex', '-1');
    const jumpToFraser = () => {
      try { fraserCard.scrollIntoView({ block: 'start' }); fraserCard.focus({ preventScroll: true }); } catch (e) { /* not available */ }
    };

    const hero = h('div', { class: 'hero' },
      h('p', { class: 'kicker' }, 'Nooksack River → Sumas Prairie'),
      h('h1', null, 'Sumas Prairie overflow watch'),
      h('p', { class: 'problem' }, 'An atmospheric river is coming. Will the Nooksack spill over toward Sumas Prairie (it did in Nov 2021 and Dec 2025), and how many hours would we have?'),
      h('p', { class: 'jump' }, 'In BC? ', h('button', { type: 'button', class: 'link-btn', onclick: jumpToFraser }, 'Jump to the Fraser Valley gauges ↓')));

    const nowCard = card('Now at North Cedarville', null);
    const chartCard = card('North Cedarville: last 7 days and forecasts', 'Stage in feet (gauge datum) with the official NWS flood stages; metres on the right axis on wider screens (1 ft = 0.3048 m).');
    const chancesCard = card('FloodLead chances of reaching each stage', null);
    const personalCard = card('Your own level', null);
    const replayCard = card('Replay: how many hours did the gauge give?', 'The same gauges in past floods: when North Cedarville crossed minor flood stage, and when water first appeared at the Overflow gauge on SR 544.');
    const ledgerCard = card('Forecast ledger', 'Every FloodLead forecast is written to an append-only, hash-chained ledger when it is issued, before the outcome is known.');

    // The demo path first; the Fraser Valley list follows the overflow-watch cards; feedback last.
    fill(main, hero, nowCard, chartCard, chancesCard, personalCard, replayCard, ledgerCard, fraserCard, feedbackBox(null));

    const pStation = api(`/v1/stations/${CEDARVILLE}`);
    const pOverflow = api(`/v1/stations/${OVERFLOW}`);
    const pObs = api(`/v1/stations/${CEDARVILLE}/observations?param=level&days=7`);
    const pNoaa = api(`/v1/official-forecasts/${NOAA_LID}`);
    const pFc = api(`/v1/stations/${CEDARVILLE}/forecast`);
    const pReplay = api('/v1/replay/overflow');
    const pLedger = api('/v1/ledger/head');
    const pFraser = api('/v1/gauges/fraser-valley');

    section(fraserCard, seq, async () => {
      const data = await pFraser;
      if (isStale(seq)) return;
      fill(fraserCard.body, fraserBlock(data));
    });

    section(nowCard, seq, async () => {
      const [st, ovf] = await Promise.all([pStation, pOverflow]);
      if (isStale(seq)) return;
      w.station = st;
      fill(nowCard.body, nowBlock(st, w), overflowBlock(ovf));
    });

    section(chartCard, seq, async () => {
      const [st, obs, noaa, fc] = await Promise.all([pStation, pObs, pNoaa, pFc]);
      if (isStale(seq)) return;
      w.fc = fc;
      const models = fc && Array.isArray(fc.models) ? fc.models.filter(Boolean) : [];
      w.model = models.length ? models[pickModelIdx(models)] : null;
      const cats = stationCategories(st || (noaa && noaa.station));
      const iss = latestIssuance(noaa);
      const obsPts = obsToPoints(obs && obs.observations, 'ft');
      const chartEl = h('div', { class: 'chart' });
      const info = h('div');
      const keyItems = [{ cls: 'sw-obs', text: 'Observed (USGS, provisional)' }];
      if (iss) keyItems.push({ cls: 'sw-noaa dashed', text: `${NOAA_LABEL}, issued ${fmtPacific(iss.issued_at)}` });
      for (const c of cats) keyItems.push({ cls: `sw-${c.key} dashed`, text: `${c.name} ${fmt(c.ft, 1)} ft` });
      keyItems.push({ cls: 'sw-personal dashed', text: 'Your level (if set)' });
      fill(chartCard.body,
        h('p', null,
          iss ? h('span', { class: 'tag tag-noaa' }, `${NOAA_LABEL} · issued ${fmtPacific(iss.issued_at)} (${fmtUtc(iss.issued_at)})`) : h('span', { class: 'muted' }, 'No NOAA NWS official forecast available right now.'),
          ' '),
        info, chartEl, legendKey(keyItems),
        obsSpanNote(obs, obsPts));
      const draw = () => {
        fill(info, w.model ? h('p', null, h('span', { class: 'tag tag-fl' }, `${FL_LABEL} — ${modelName(w.model.model)}: median and 10–90 % band`)) : h('p', { class: 'muted' }, 'No FloodLead forecast issued yet — hourly issuance starts soon.'));
        removeChart(w.chart);
        if (isStale(seq)) return;
        w.chart = levelChart(chartEl, {
          unit: 'ft',
          mAxis: true,
          obs: obsPts,
          noaa: iss ? { points: noaaPoints(iss, 'ft'), label: `NOAA NWS official forecast (unmodified), issued ${fmtPacificShort(iss.issued_at)}` } : null,
          fl: flSeries(w.model, 'ft'),
          hlines: () => cats.map((c) => ({ value: c.ft, color: c.color, label: `${c.name} ${fmt(c.ft, 1)} ft`, dash: [6, 4] }))
            .concat(isNum(w.personalFt) ? [{ value: w.personalFt, color: COLORS.personal, label: `Your level ${fmt(w.personalFt, 1)} ft`, dash: [2, 3], width: 2 }] : []),
          vlines: () => [nowLine(snapOf(obs))],
        });
      };
      draw();
      w.redrawChart = draw;
      w.onPersonal.push(() => { if (w.chart) w.chart.setData(w.chart.data, true); });
    });

    section(chancesCard, seq, async () => {
      const fc = await pFc;
      if (isStale(seq)) return;
      fill(chancesCard.body, chancesBlock(fc, true, (m) => { w.model = m; if (w.redrawChart) w.redrawChart(); }));
    });

    section(personalCard, seq, async () => {
      const [st, fc, replay] = await Promise.all([pStation, pFc, pReplay]);
      if (isStale(seq)) return;
      personalBlock(personalCard.body, st, fc, replay, w);
    });

    section(replayCard, seq, async () => {
      const replay = await pReplay;
      if (isStale(seq)) return;
      replayBlock(replayCard.body, replay, seq);
    });

    section(ledgerCard, seq, async () => {
      const [head, fc] = await Promise.all([pLedger, pFc]);
      if (isStale(seq)) return;
      fill(ledgerCard.body, ledgerBlock(head, fc));
    });
  }

  function obsSpanNote(obs, pts) {
    const real = pts.filter((p) => isNum(p[1]));
    if (!obs || !real.length) return h('p', { class: 'muted' }, 'No recent observations available.');
    const first = new Date(real[0][0] * 1000);
    const last = new Date(real[real.length - 1][0] * 1000);
    const hours = (last - first) / 3.6e6;
    return h('p', { class: 'muted' },
      `Observed: ${real.length} readings from ${fmtPacific(first)} to ${fmtPacific(last)} (${fmtDuration(hours * 60)}). `,
      hours < 6 * 24 ? 'Less than 7 days of data were returned. ' : '',
      'Drag across the chart to zoom; double-click to reset.');
  }

  function stageList(cats, currentFt, personalFt) {
    const items = cats.map((c) => {
      const diff = c.ft - currentFt;
      const reached = diff <= 0;
      return h('li', { class: `stage-${c.key}${reached ? ' reached' : ''}` },
        h('span', null, `${c.name} stage `, h('strong', { class: 'num' }, `${fmt(c.ft, 1)} ft`), h('span', { class: 'muted num' }, ` (${fmt(c.m, 2)} m)`)),
        h('span', { class: 'num' }, reached
          ? `reached: ${fmt(-diff, 2)} ft above (${fmt(ftToM(-diff), 2)} m)`
          : `${fmt(diff, 2)} ft below (${fmt(ftToM(diff), 2)} m)`));
    });
    if (isNum(personalFt)) {
      const diff = personalFt - currentFt;
      items.push(h('li', { class: `stage-personal${diff <= 0 ? ' reached' : ''}` },
        h('span', null, 'Your level ', h('strong', { class: 'num' }, `${fmt(personalFt, 1)} ft`)),
        h('span', { class: 'num' }, diff <= 0 ? `reached: ${fmt(-diff, 2)} ft above` : `${fmt(diff, 2)} ft below`)));
    }
    return h('ul', { class: 'stages' }, items);
  }

  function nowBlock(st, w) {
    if (!st) return placeholder('North Cedarville (usgs:12210700) is not available right now.');
    const lv = st.latest && st.latest.level;
    const cats = stationCategories(st);
    const wrap = h('div');
    const draw = () => {
      if (!lv || !isNum(lv.value)) {
        fill(wrap, h('h3', null, titleCase(st.name)), placeholder('No recent level reading.'));
        return;
      }
      const ft = mToFt(lv.value);
      fill(wrap,
        h('h3', null, titleCase(st.name), ' ', h('span', { class: 'muted' }, `(${st.station_id})`)),
        h('div', { class: 'now-row' }, h('span', { class: 'big' }, `${fmt(ft, 2)} ft`), h('span', { class: 'big-m' }, `${fmt(lv.value, 2)} m`)),
        h('p', { class: 'meta' }, 'Observed ', timeLine(lv.ts, true, snapOf(st)), ' ', provisionalTag(), ' (USGS)'),
        cats.length ? stageList(cats, ft, w.personalFt) : h('p', { class: 'muted' }, 'No official flood stages published for this gauge.'),
        cats.length ? h('p', { class: 'muted' }, `Flood stages: NOAA NWS official flood categories for ${(st.official_thresholds && st.official_thresholds.lid) || NOAA_LID}.`) : null);
    };
    draw();
    w.onPersonal.push(draw);
    return wrap;
  }

  function overflowBlock(st) {
    const box = h('div', { class: 'sub-gauge' });
    if (!st) return fill(box, h('h3', null, 'Overflow gauge at SR 544'), placeholder('The Overflow gauge (usgs:12211195) is not available right now.'));
    const lv = st.latest && st.latest.level;
    const cats = stationCategories(st);
    appendKids(box, h('h3', null, titleCase(st.name), ' ', h('span', { class: 'muted' }, `(${st.station_id})`)));
    if (!lv || !isNum(lv.value)) {
      appendKids(box, h('p', { class: 'muted' }, 'No recent reading.'));
    } else {
      const ft = mToFt(lv.value);
      appendKids(box,
        h('div', { class: 'now-row' }, h('span', { class: 'big' }, `${fmt(ft, 2)} ft`), h('span', { class: 'big-m' }, `${fmt(lv.value, 2)} m`)),
        h('p', { class: 'meta' }, 'Observed ', timeLine(lv.ts, true, snapOf(st)), ' ', provisionalTag(), ' (USGS)'),
        cats.length ? stageList(cats, ft, null) : null);
    }
    if (lv && isNum(lv.value)) {
      const ft = mToFt(lv.value);
      const action = cats.find((c) => c.key === 'action');
      const actionFt = action && isNum(action.ft) ? action.ft : 3.6;
      appendKids(box, h('p', { class: ft >= actionFt ? 'notice' : 'muted' }, ft >= actionFt
        ? `At or above its NWS action stage (${fmt(actionFt, 1)} ft): water may be crossing the overflow path.`
        : `Below its NWS action stage (${fmt(actionFt, 1)} ft): no overflow. Since 2026-10-01 this gauge reports continuously at about 3.5 ft when the overflow path is dry; before that it reported only while water was flowing.`));
    }
    appendKids(box, h('p', { class: 'muted' }, 'This USGS gauge records Nooksack overflow water crossing Highway 544 at Everson, on the overflow path north toward Sumas and Sumas Prairie.'));
    return box;
  }

  function personalBlock(body, st, fc, replay, w) {
    const models = fc && Array.isArray(fc.models) ? fc.models.filter(Boolean) : [];
    const lv = st && st.latest && st.latest.level;
    const currentFt = lv && isNum(lv.value) ? mToFt(lv.value) : null;
    const input = h('input', { type: 'number', id: 'personal-level', inputmode: 'decimal', step: '0.1', min: '0', max: '400', placeholder: 'e.g. 147.0', value: isNum(w.personalFt) ? String(w.personalFt) : null, 'aria-describedby': 'personal-note' });
    const result = h('div', { 'aria-live': 'polite' });
    const setLevel = (v, writeInput) => {
      w.personalFt = isNum(v) ? Math.round(v * 100) / 100 : null;
      savePref(PERSONAL_KEY, w.personalFt);
      if (writeInput) input.value = isNum(w.personalFt) ? String(w.personalFt) : '';
      renderResult();
      for (const fn of w.onPersonal) { try { fn(); } catch (e) { console.error(e); } }
    };
    let t = null;
    input.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => {
        const raw = input.value.trim();
        const v = raw === '' ? null : parseFloat(raw);
        if (raw !== '' && !(isNum(v) && v >= 0 && v <= 400)) { fill(result, h('p', { class: 'error' }, 'Please enter a stage in feet, for example 147.0.')); return; }
        setLevel(v, false);
      }, 250);
    });
    const clearBtn = h('button', { type: 'button', onclick: () => setLevel(null, true) }, 'Clear');

    let suggest = null;
    const sg = suggestedLevel(replay, st);
    if (sg) {
      suggest = h('div', { class: 'suggest' },
        h('p', null, h('strong', null, `Suggested: ${fmt(sg.ft, 1)} ft`), ' ', h('span', { class: 'tag tag-official' }, sg.label), ' ',
          h('button', { type: 'button', class: 'small', onclick: () => setLevel(sg.ft, true) }, 'Use this level')),
        sg.text ? h('p', null, sg.text) : null,
        h('p', { class: 'muted' }, 'Not every flood that reached this stage spilled over, and no single level separates the floods that did from those that did not (see the replay below).'));
    }

    function renderResult() {
      const L = w.personalFt;
      if (!isNum(L)) { fill(result, h('p', { class: 'muted' }, 'Enter a level to see the chance of reaching it within the next 48 hours.')); return; }
      const parts = [];
      if (isNum(currentFt)) {
        const diff = L - currentFt;
        parts.push(h('p', { class: 'result-line' }, 'North Cedarville is ', h('strong', null, diff > 0 ? `${fmt(diff, 2)} ft below` : `${fmt(-diff, 2)} ft above`), ` your level of ${fmt(L, 2)} ft (observed `, timeLine(lv.ts, false, snapOf(st)), ').'));
      }
      if (!models.length) {
        parts.push(placeholder('No FloodLead forecast issued yet — hourly issuance starts soon. Your level is saved on this device.'));
        fill(result, parts);
        return;
      }
      const Lm = ftToM(L);
      const perModel = models.map((m) => {
        const hz = (m.horizons || []).slice().sort((a, b) => a.h - b.h).map((z) => ({ z, r: pExceedFromQuantiles(z.qmax, Lm) }));
        const first = (thr) => { const f = hz.find((x) => isNum(x.r.p) && x.r.p >= thr); return f ? `within ${f.z.h} h (by ${fmtPacificShort(f.z.valid_at)})` : 'not within 48 h'; };
        return { m, hz, p10: first(0.1), p50: first(0.5) };
      });
      for (const pm of perModel) {
        parts.push(h('p', { class: 'result-line' }, h('strong', null, modelName(pm.m.model)), ': at least 10 % chance ', h('strong', null, pm.p10), '; at least 50 % chance ', h('strong', null, pm.p50), '.'));
      }
      const allH = Array.from(new Set(perModel.flatMap((pm) => pm.hz.map((x) => x.z.h)))).sort((a, b) => a - b);
      const rows = allH.map((hh) => {
        const ref = perModel.map((pm) => pm.hz.find((x) => x.z.h === hh)).find(Boolean);
        return h('tr', null,
          h('td', null, `within ${hh} h`, ref ? h('small', { class: 'muted' }, ` by ${fmtPacificShort(ref.z.valid_at)}`) : null),
          perModel.map((pm) => { const x = pm.hz.find((y) => y.z.h === hh); return h('td', { class: x ? pClass(x.r.p) : 'p' }, x ? x.r.text : '—'); }));
      });
      parts.push(tableBox(h('table', { class: 'personal-chances' },
        h('thead', null, h('tr', null, h('th', null, 'Chance of reaching your level'), perModel.map((pm) => h('th', { class: 'p wrap' }, modelName(pm.m.model))))),
        h('tbody', null, rows))));
      parts.push(h('p', { class: 'model-explain' }, MODEL_EXPLAIN));
      parts.push(h('p', null, h('span', { class: 'tag tag-fl' }, 'interpolated from FloodLead baseline quantiles'), ' ',
        h('span', { class: 'muted' }, `forecast data as of ${fmtPacific(models[0].data_as_of)}`)));
      fill(result, parts);
    }

    fill(body,
      h('p', null, 'Type the stage that matters to you — for example when your field, driveway or road starts to flood.'),
      h('label', { for: 'personal-level' }, 'Your action level (ft)'),
      h('div', { class: 'input-row' }, input, h('span', null, 'ft at North Cedarville'), clearBtn),
      h('p', { id: 'personal-note', class: 'muted' }, 'Your level stays on this device (browser storage only). It is never sent to the server.'),
      suggest,
      result);
    renderResult();
  }

  /** The suggested personal level. New API shape: the official NWS minor flood stage with its label
   *  and rule text from the replay summary. Older shape (an empirical onset level): replaced here by the
   *  official minor flood stage, with the same rule built from the summary counts. */
  function suggestedLevel(replay, st) {
    const s = replay && replay.summary;
    if (!s) return null;
    const label = typeof s.suggested_label === 'string' ? s.suggested_label : '';
    const newShape = typeof s.separation_text === 'string' || Array.isArray(s.peaks_with_overflow_ft);
    if (newShape && isNum(s.suggested_personal_level_ft) && !/empirical/i.test(label)) {
      return { ft: s.suggested_personal_level_ft, label: label || 'NWS minor flood stage (official)', text: typeof s.suggested_text === 'string' ? s.suggested_text : '' };
    }
    const minor = stationCategories(st).find((c) => c.key === 'minor');
    const ced = replay.gauges && replay.gauges.cedarville;
    const ft = minor ? minor.ft : (ced && ced.stages_ft && isNum(ced.stages_ft.minor) ? ced.stages_ft.minor : null);
    if (!isNum(ft)) return null;
    const hm = s.hours_after_minor;
    let text = '';
    if (isNum(s.events_with_overflow) && isNum(s.events_with_gauge)) {
      text = `${s.events_with_overflow} of ${s.events_with_gauge} minor-stage events since Nov 2015 were followed by water on the overflow path`
        + (hm && isNum(hm.median) && isNum(hm.min) && isNum(hm.max) ? `, a median ${fmt(hm.median, 1)} h later (${fmt(hm.min, 1)}–${fmt(hm.max, 1)} h).` : '.');
    }
    return { ft: Math.round(ft * 10) / 10, label: 'NWS minor flood stage (official)', text };
  }

  /** Peaks at North Cedarville in events with and without an overflow (summary fields if the API has
   *  them, otherwise derived from the events in the overflow-gauge era). */
  function overflowPeaks(replay, events) {
    const s = replay.summary || {};
    let withP = Array.isArray(s.peaks_with_overflow_ft) ? s.peaks_with_overflow_ft.filter(isNum) : null;
    let withoutP = Array.isArray(s.peaks_without_overflow_ft) ? s.peaks_without_overflow_ft.filter(isNum) : null;
    if (!withP || !withoutP) {
      const era = events.filter((e) => e.overflow_gauge_operating !== false && isNum(e.peak_ft));
      withP = era.filter((e) => e.overflow).map((e) => e.peak_ft);
      withoutP = era.filter((e) => !e.overflow).map((e) => e.peak_ft);
    }
    withP = withP.slice().sort((a, b) => a - b);
    withoutP = withoutP.slice().sort((a, b) => a - b);
    const range = (arr, r) => (r && isNum(r.min) && isNum(r.max) ? r : (arr.length ? { min: arr[0], max: arr[arr.length - 1] } : null));
    const rW = range(withP, s.peak_range_with_overflow_ft);
    const rN = range(withoutP, s.peak_range_without_overflow_ft);
    const overlap = !!(rW && rN && rW.min <= rN.max && rN.min <= rW.max);
    let text = typeof s.separation_text === 'string' && s.separation_text ? s.separation_text : '';
    if (!text && rW && rN) {
      text = overlap
        ? `Peaks overlap (overflow ${fmt(rW.min, 1)}–${fmt(rW.max, 1)} ft, no overflow ${fmt(rN.min, 1)}–${fmt(rN.max, 1)} ft): no single level separates them.`
        : `Peaks do not overlap in this small sample (overflow ${fmt(rW.min, 1)}–${fmt(rW.max, 1)} ft, no overflow ${fmt(rN.min, 1)}–${fmt(rN.max, 1)} ft).`;
    }
    return { withP, withoutP, rW, rN, overlap, text };
  }

  function peaksBlock(pk, minorFt) {
    if (!pk.withP.length && !pk.withoutP.length) return null;
    const all = pk.withP.concat(pk.withoutP, isNum(minorFt) ? [minorFt] : []);
    const lo = Math.floor((Math.min(...all) - 0.2) * 2) / 2;
    const hi = Math.ceil((Math.max(...all) + 0.2) * 2) / 2;
    const pos = (v) => `${(100 * (v - lo) / (hi - lo)).toFixed(2)}%`;
    const row = (name, cls, vals) => {
      const track = h('div', { class: 'peak-track' });
      if (isNum(minorFt)) { const m = h('span', { class: 'peak-minor' }); m.style.left = pos(minorFt); track.appendChild(m); }
      for (const v of vals) { const d = h('span', { class: `peak-dot ${cls}`, title: `${fmt(v, 2)} ft` }); d.style.left = pos(v); track.appendChild(d); }
      return h('div', { class: 'peak-row' }, h('span', { class: 'peak-name' }, `${name} (${vals.length})`), track);
    };
    const ticks = h('div', { class: 'peak-axis' });
    for (let v = Math.ceil(lo); v <= hi; v += 1) { const t = h('span', null, `${v}`); t.style.left = pos(v); ticks.appendChild(t); }
    const list = (vals) => (vals.length ? vals.map((v) => fmt(v, 2)).join(', ') + ' ft' : 'none');
    return h('div', { class: 'peaks' },
      h('h3', null, 'Peak at North Cedarville: floods with and without an overflow'),
      h('div', { class: 'peak-strip', 'aria-hidden': 'true' },
        row('Overflow followed', 'with', pk.withP),
        row('No overflow', 'without', pk.withoutP),
        h('div', { class: 'peak-row' }, h('span', { class: 'peak-name' }, 'ft'), ticks)),
      h('ul', { class: 'peak-lists' },
        h('li', null, h('span', { class: 'swatch sw-ovf' }), ` Overflow followed (${pk.withP.length}): `, h('span', { class: 'num' }, list(pk.withP))),
        h('li', null, h('span', { class: 'swatch sw-marker' }), ` No overflow (${pk.withoutP.length}): `, h('span', { class: 'num' }, list(pk.withoutP))),
        isNum(minorFt) ? h('li', null, h('span', { class: 'swatch sw-minor dashed' }), ` NWS minor flood stage ${fmt(minorFt, 1)} ft`) : null),
      pk.text ? h('p', null, pk.text) : null,
      pk.overlap ? h('p', null, h('strong', null, 'No single North Cedarville level separates the floods that spilled over from those that did not.'),
        ' Some floods peaked higher without an overflow than others that had one, so treat any level as a prompt to watch, not as a trigger.') : null,
      h('p', { class: 'muted' }, 'Events since the Overflow gauge began recording (Nov 2015), each event’s highest stage at North Cedarville.'));
  }

  function replayBlock(body, replay, seq) {
    if (!replay || !Array.isArray(replay.events)) {
      fill(body, placeholder('The flood replay is being prepared and will appear here soon.'));
      return;
    }
    const g = replay.gauges || {};
    const ced = g.cedarville || {};
    const ovf = g.overflow || {};
    const cedId = ced.station_id || CEDARVILLE;
    const ovfId = ovf.station_id || OVERFLOW;
    const events = replay.events.filter(Boolean).slice().sort((a, b) => String(a.event_id).localeCompare(String(b.event_id), 'en-CA'));
    const s = replay.summary || {};
    const minorFt = ced.stages_ft && isNum(ced.stages_ft.minor) ? ced.stages_ft.minor : 146.5;

    const answer = h('div');
    const chartEl = h('div', { class: 'chart' });
    const chartNote = h('div');
    let selected = null;
    let chart = null;
    const rowsById = new Map();

    const summaryP = h('p', null,
      isNum(s.events_total) ? `${s.events_total} events in the gauge record crossed minor flood stage (${fmt(minorFt, 1)} ft) at North Cedarville. ` : '',
      isNum(s.events_with_gauge) ? `The Overflow gauge was operating in ${s.events_with_gauge}` : '',
      isNum(s.events_with_overflow) ? `; overflow was recorded in ${s.events_with_overflow}. ` : (isNum(s.events_with_gauge) ? '. ' : ''),
      s.hours_after_minor && isNum(s.hours_after_minor.median) ? `Median time from minor stage to overflow: ${fmtDuration(s.hours_after_minor.median * 60)} (range ${fmtDuration(s.hours_after_minor.min * 60)} – ${fmtDuration(s.hours_after_minor.max * 60)}). ` : '',
      s.onset_cedarville_ft && isNum(s.onset_cedarville_ft.median) ? `North Cedarville stood at ${fmt(s.onset_cedarville_ft.min, 1)}–${fmt(s.onset_cedarville_ft.max, 1)} ft (median ${fmt(s.onset_cedarville_ft.median, 1)} ft) when the overflow began.` : '');
    const peaks = peaksBlock(overflowPeaks(replay, events), minorFt);
    const onsetNote = typeof s.onset_note === 'string' && s.onset_note ? h('p', { class: 'muted' }, s.onset_note) : null;

    const quick = h('div', { class: 'tabs' });
    const quickBtns = [];
    for (const id of DEFAULT_EVENTS) {
      const ev = events.find((e) => e.event_id === id);
      if (!ev) continue;
      const b = h('button', { type: 'button', onclick: () => select(ev) }, id.startsWith('2021') ? `Nov 2021 (${id})` : id.startsWith('2025') ? `Dec 2025 (${id})` : id);
      b.eventId = id;
      quickBtns.push(b);
      quick.appendChild(b);
    }

    const head = h('tr', null, ['Event', 'Minor stage crossed', 'Overflow first record', 'Hours after minor', 'Cedarville at onset', 'Peak at Cedarville', ''].map((t) => h('th', null, t)));
    const rows = events.map((ev) => {
      const o = ev.overflow;
      let ovCell;
      let hoursCell = '—';
      let onsetCell = '—';
      if (o) {
        ovCell = h('span', null, fmtPacificYear(o.first_record_at), h('small', { class: 'muted' }, h('br'), `${fmt(o.first_record_ft, 2)} ft, max ${fmt(o.max_ft, 2)} ft`));
        hoursCell = isNum(o.hours_after_minor) ? fmtDuration(o.hours_after_minor * 60) : '—';
        onsetCell = isNum(o.cedarville_ft_at_onset) ? `${fmt(o.cedarville_ft_at_onset, 2)} ft` : '—';
      } else {
        ovCell = h('span', { class: 'muted' }, ev.overflow_gauge_operating === false ? 'gauge not yet operating' : 'none recorded');
      }
      const tr = h('tr', { class: 'clickable' },
        h('td', null, h('strong', null, ev.event_id || '—'), ev.note ? h('small', { class: 'muted' }, h('br'), ev.note) : null),
        h('td', null, fmtPacificYear(ev.minor_first)),
        h('td', null, ovCell),
        h('td', { class: 'p' }, hoursCell),
        h('td', { class: 'p' }, onsetCell),
        h('td', { class: 'p' }, isNum(ev.peak_ft) ? `${fmt(ev.peak_ft, 2)} ft` : '—', ev.peak_at ? h('small', { class: 'muted' }, h('br'), fmtDate(ev.peak_at)) : null),
        h('td', null, h('button', { type: 'button', class: 'small', onclick: (e) => { e.stopPropagation(); select(ev); } }, 'Chart')));
      tr.addEventListener('click', () => select(ev));
      rowsById.set(ev.event_id, tr);
      return tr;
    });

    const caveats = Array.isArray(replay.caveats) && replay.caveats.length
      ? h('div', null, h('h3', null, 'Caveats'), h('ul', { class: 'caveats' }, replay.caveats.map((c) => h('li', null, String(c)))))
      : null;

    fill(body,
      summaryP,
      onsetNote,
      peaks,
      h('h3', null, 'Pick a flood'), quick,
      answer, chartEl, legendKey([
        { cls: 'sw-obs', text: 'North Cedarville stage (ft, left axis)' },
        { cls: 'sw-ovf', text: 'Overflow at SR 544 stage (ft, right axis)' },
        { cls: 'sw-minor dashed', text: `Minor flood stage ${fmt(minorFt, 1)} ft` },
        { cls: 'sw-marker dotted', text: 'Minor crossed / overflow began' },
      ]), chartNote,
      h('h3', null, `All ${events.length} events`),
      tableBox(h('table', null, h('thead', null, head), h('tbody', null, rows))),
      caveats,
      replay.generated_at ? h('p', { class: 'muted' }, `Computed from USGS historical data (approved where available), ${fmtPacific(replay.generated_at)}. Not what was visible in real time.`) : null);

    async function select(ev) {
      selected = ev;
      for (const [id, tr] of rowsById) tr.classList.toggle('selected', id === ev.event_id);
      for (const b of quickBtns) b.setAttribute('aria-selected', b.eventId === ev.event_id ? 'true' : 'false');
      const o = ev.overflow;
      const minorT = toDate(ev.minor_first);
      const onsetT = o ? toDate(o.first_record_at) : null;
      let lead = null;
      if (minorT && onsetT) lead = (onsetT - minorT) / 60000;
      else if (o && isNum(o.hours_after_minor)) lead = o.hours_after_minor * 60;
      fill(answer,
        h('p', { class: 'answer lead' }, `${ev.event_id}: `,
          o ? `How many hours the gauge gave before the overflow began: ${fmtDuration(lead)}` : (ev.overflow_gauge_operating === false ? 'The Overflow gauge was not yet operating in this event.' : 'No overflow was recorded at SR 544 in this event.')),
        h('p', { class: 'muted' },
          `Minor stage crossed ${fmtPacificYear(ev.minor_first)}`,
          o ? `; overflow first recorded ${fmtPacificYear(o.first_record_at)} at ${fmt(o.first_record_ft, 2)} ft, with North Cedarville at ${fmt(o.cedarville_ft_at_onset, 2)} ft` : '',
          isNum(ev.peak_ft) ? `; peak ${fmt(ev.peak_ft, 2)} ft on ${fmtPacificYear(ev.peak_at)}.` : '.'));
      fill(chartNote);
      removeChart(chart);
      chart = null;
      fill(chartEl, h('p', { class: 'loading' }, 'Loading the flood’s gauge records…'));
      const sr = await api(`/v1/replay/overflow/${ev.event_id}/series`);
      if (isStale(seq) || selected !== ev) return;
      const series = sr && sr.series ? sr.series : null;
      if (!series || (!series[cedId] && !series[ovfId])) {
        fill(chartEl, placeholder('The gauge records for this flood are not available yet.'));
        return;
      }
      const toPts = (arr) => withGaps((arr || []).map((p) => { const d = toDate(p && p[0]); return d && isNum(p[1]) ? [tSec(d), p[1]] : null; }).filter(Boolean).sort((a, b) => a[0] - b[0]), 3 * 3600);
      chart = replayChart(chartEl, toPts(series[cedId]), toPts(series[ovfId]), minorFt, minorT, onsetT);
      if (sr.window) fill(chartNote, h('p', { class: 'muted' }, `Window: ${fmtPacificYear(sr.window.start)} to ${fmtPacificYear(sr.window.end)}. Values in feet as published by USGS.`));
    }

    const def = events.find((e) => e.event_id === DEFAULT_EVENTS[0]) || events.find((e) => e.overflow) || events[events.length - 1];
    if (def) select(def);
    else fill(answer, placeholder('No flood events in the record yet.'));
  }

  function replayChart(container, ced, ovf, minorFt, minorT, onsetT) {
    if (typeof window.uPlot !== 'function') { fill(container, placeholder('The chart library did not load.')); return null; }
    const data = alignSeries([ced, ovf]);
    if (!data[0].length) { fill(container, placeholder('No gauge records for this flood.')); return null; }
    const size = chartSize(container);
    const narrow = size.width < 480;
    const ov = {
      hlines: () => [{ value: minorFt, color: COLORS.minor, label: `Minor ${fmt(minorFt, 1)} ft`, dash: [6, 4] }],
      vlines: () => [
        minorT ? { t: tSec(minorT), color: COLORS.marker, label: 'minor crossed', dash: [3, 3], row: 0 } : null,
        onsetT ? { t: tSec(onsetT), color: COLORS.ovf, label: 'overflow began', dash: [3, 3], row: 1 } : null,
      ].filter(Boolean),
    };
    const opts = {
      width: size.width,
      height: size.height,
      tzDate: (ts) => uPlot.tzDate(new Date(ts * 1e3), TZ),
      scales: {
        x: { time: true },
        y: { range: (u, mn, mx) => { const a = Math.min(isNum(mn) ? mn : minorFt, minorFt); const b = Math.max(isNum(mx) ? mx : minorFt, minorFt); const pad = Math.max((b - a) * 0.06, 0.3); return [a - pad, b + pad]; } },
        ovf: { range: (u, mn, mx) => [0, Math.max(isNum(mx) ? mx : 1, 1) * 1.1] },
      },
      axes: [
        Object.assign({}, X_AXIS),
        { scale: 'y', label: narrow ? undefined : 'North Cedarville (ft)', stroke: COLORS.axis, size: narrow ? 46 : 58, grid: { stroke: COLORS.grid, width: 1 }, values: (u, sp) => sp.map((v) => v.toFixed(1)) },
        { scale: 'ovf', side: 1, label: narrow ? undefined : 'Overflow SR 544 (ft)', stroke: COLORS.ovf, size: narrow ? 36 : 50, grid: { show: false }, values: (u, sp) => sp.map((v) => v.toFixed(1)) },
      ],
      series: [
        Object.assign({}, X_SERIES),
        { label: 'North Cedarville', scale: 'y', stroke: COLORS.obs, width: 2, points: { show: false }, value: (u, v) => (isNum(v) ? `${v.toFixed(2)} ft` : '—') },
        { label: 'Overflow SR 544', scale: 'ovf', stroke: COLORS.ovf, width: 2, points: { show: false }, value: (u, v) => (isNum(v) ? `${v.toFixed(2)} ft` : '—') },
      ],
      legend: { live: true },
      cursor: { drag: { x: true, y: false } },
      hooks: { draw: [(u) => drawOverlays(u, ov)] },
    };
    clear(container);
    const u = new uPlot(opts, data, container);
    state.charts.push(u);
    return u;
  }

  function ledgerBlock(head, fc) {
    const models = fc && Array.isArray(fc.models) ? fc.models.filter(Boolean) : [];
    if (!head) {
      return h('div', null, placeholder('Ledger starts with the first hourly issuance.'));
    }
    const a = head.anchor;
    let anchor;
    if (a) {
      anchor = h('span', null, h('span', { class: `dot ${a.status || ''}` }), `${a.status || 'unknown'}`,
        isNum(a.seq) ? ` · seq ${a.seq}` : '',
        a.anchored_at ? h('span', null, ' · anchored ', timeLine(a.anchored_at, false, snapOf(head))) : '',
        a.commit_url ? h('span', null, ' · ', extLink(a.commit_url, 'commit on GitHub')) : '');
    } else {
      anchor = h('span', { class: 'muted' }, 'not anchored yet');
    }
    const items = models.map((m) => h('li', null, `${modelName(m.model)}: seq ${isNum(m.seq) ? m.seq : '—'} · `, hashView(m.entry_hash), m.created_at ? h('small', { class: 'muted' }, ' · issued ', fmtPacific(m.created_at)) : null));
    return h('div', null,
      h('dl', { class: 'kv' },
        h('dt', null, 'Head'), h('dd', null, `seq ${isNum(head.seq) ? head.seq : '—'} · `, hashView(head.entry_hash)),
        h('dt', null, 'Head written'), h('dd', null, head.created_at ? timeLine(head.created_at, true, snapOf(head)) : '—', head.entry_type ? ` · ${head.entry_type}` : ''),
        h('dt', null, 'Public anchor'), h('dd', null, anchor)),
      h('h3', null, 'Forecasts on this page'),
      items.length ? h('ul', null, items) : h('p', { class: 'muted' }, 'No FloodLead forecast on screen yet.'),
      h('p', null, head.spec_url ? extLink(head.spec_url, 'How the ledger works and how to verify it (ledger spec)') : null));
  }

  /** "Fraser Valley gauges" (GET /v1/gauges/fraser-valley): latest level, data age and the position
   *  against each gauge's typical yearly peak, in the API's order. */
  function fraserBlock(data) {
    const gauges = data && Array.isArray(data.gauges) ? data.gauges.filter(Boolean) : null;
    if (!gauges) return placeholder('The Fraser Valley gauge list is not available right now. Use All stations to find a gauge.');
    if (!gauges.length) return placeholder('No Fraser Valley gauges in the list yet. Use All stations to find a gauge.');
    const snap = snapOf(data);
    return h('div', null,
      h('p', { class: 'card-sub' }, typeof data.label === 'string' && data.label ? data.label : TYPICAL_PEAK_LABEL),
      h('ul', { class: 'gauge-list' }, gauges.map((g) => gaugeRow(g, snap))),
      h('p', { class: 'muted' }, 'Levels are ECCC provisional real-time data in metres above each gauge’s own reference point, so levels cannot be compared between gauges. Open a gauge for its 7-day chart and FloodLead forecast, or ',
        h('a', { href: '#/stations' }, 'search all stations'), '.'));
  }

  function gaugeRow(g, snap) {
    const id = typeof g.station_id === 'string' ? g.station_id : '';
    const name = (typeof g.short_name === 'string' && g.short_name) || titleCase(g.name) || id || 'Unnamed gauge';
    const lt = g.latest && isNum(g.latest.level_m) ? g.latest : null;
    const tp = g.typical_peak && isNum(g.typical_peak.value_m) ? g.typical_peak : null;
    let age = null;
    if (lt && toDate(lt.ts)) age = ageSpan(lt.ts, snap);
    else if (lt && isNum(lt.age_min)) age = `${fmtDuration(lt.age_min)} old`;

    let pos;
    if (tp) {
      const below = isNum(tp.below_m) ? tp.below_m : (lt ? tp.value_m - lt.level_m : null);
      const years = isNum(tp.first_year) && isNum(tp.last_year) ? `, ${tp.first_year}–${tp.last_year}` : '';
      const basis = isNum(tp.n_years) ? `median of ${tp.n_years} yearly peaks${years}` : 'FloodLead-derived';
      const flagged = tp.status && tp.status !== 'ok';
      pos = [
        h('p', { class: 'gauge-pos' },
          isNum(below) ? h('strong', { class: 'num' }, below < 0 ? `${fmt(-below, 2)} m above typical yearly peak` : `${fmt(below, 2)} m below typical yearly peak`) : h('span', { class: 'muted' }, 'Position unknown (no recent level)'),
          h('span', { class: 'muted num' }, ` · typical yearly peak ${fmt(tp.value_m, 2)} m (${basis})`)),
        flagged ? h('p', { class: 'gauge-note' }, h('span', { class: 'tag tag-check' }, 'check'), ' ', String(tp.flag || `status: ${tp.status}`)) : null,
      ];
    } else {
      pos = h('p', { class: 'gauge-note' }, 'No typical yearly peak', typeof g.typical_peak_note === 'string' && g.typical_peak_note ? ` (${g.typical_peak_note})` : '', '.');
    }
    const note = typeof g.note === 'string' && g.note ? g.note : (g.tidal ? 'Tidal gauge: the level rises and falls with the tide.' : '');
    return h('li', null,
      h('div', { class: 'gauge-head' },
        h('span', null,
          STATION_ID_RE.test(id) ? h('a', { class: 'name', href: stationHref(id) }, name) : h('span', { class: 'name' }, name),
          g.tidal ? [' ', h('span', { class: 'tag tag-tidal' }, 'tidal')] : null,
          h('br'), h('span', { class: 'id' }, id)),
        h('span', { class: 'lvl' }, lt ? `${fmt(lt.level_m, 2)} m` : h('span', { class: 'muted' }, 'no recent data'), age ? [h('br'), h('small', { class: 'muted' }, age)] : null)),
      pos,
      note ? h('p', { class: 'gauge-note' }, note) : null);
  }

  // ---------------------------------------------------------------------------------------------
  // Screen 2: station picker
  // ---------------------------------------------------------------------------------------------
  function latestOf(st) {
    const l = st && st.latest ? st.latest : {};
    return l.level && isNum(l.level.value) ? l.level : null;
  }
  function levelText(st, lv) {
    if (!lv) return 'no recent level';
    if (isUsStation(st)) return `${fmt(mToFt(lv.value), 2)} ft · ${fmt(lv.value, 2)} m`;
    return `${fmt(lv.value, 3)} m`;
  }

  function renderStations(seq) {
    const main = document.getElementById('app');
    document.title = 'FloodLead BC: all stations';
    const input = h('input', { type: 'search', id: 'station-search', placeholder: 'Search by name or ID, e.g. Nooksack, Fraser, 08MH024', autocomplete: 'off' });
    const count = h('p', { class: 'count-line' }, 'Loading stations…');
    const list = h('ul', { class: 'station-list' });
    const c = card(null, null);
    fill(c.body, h('label', { for: 'station-search' }, 'Find a gauge'), input, count, list);
    fill(main,
      h('div', { class: 'hero' }, h('h1', null, 'All stations'),
        h('p', null, 'Every river gauge FloodLead archives: Water Survey of Canada (ECCC) real-time gauges across BC and USGS gauges on the Nooksack and Sumas. Levels are provisional real-time data.')),
      c, feedbackBox(null));
    section(c, seq, async () => {
      const data = await api('/v1/stations?limit=2000');
      if (isStale(seq)) return;
      const stations = data && Array.isArray(data.stations) ? data.stations.filter(Boolean) : [];
      if (!stations.length) { fill(count, ''); fill(list, placeholder('The station list is not available right now.')); return; }
      stations.sort((a, b) => (isUsStation(b) - isUsStation(a)) || String(a.name || '').localeCompare(String(b.name || ''), 'en-CA'));
      const render = () => {
        const q = input.value.trim().toLowerCase();
        const hits = q ? stations.filter((s) => `${s.name || ''} ${s.station_id || ''} ${s.native_id || ''} ${s.region || ''}`.toLowerCase().includes(q)) : stations;
        fill(count, `${hits.length} of ${stations.length} stations`);
        fill(list, hits.map((s) => {
          const lv = latestOf(s);
          return h('li', null, h('a', { href: stationHref(s.station_id) },
            h('span', null, h('span', { class: 'name' }, titleCase(s.name) || s.station_id), h('br'),
              h('span', { class: 'id' }, `${s.station_id} · ${s.region || ''}${s.has_official_thresholds ? ' · NWS flood stages' : ''}`)),
            h('span', { class: 'lvl' }, levelText(s, lv), lv ? h('br') : null, lv ? h('small', { class: 'muted' }, ageSpan(lv.ts, snapOf(data))) : null)));
        }));
      };
      let t = null;
      input.addEventListener('input', () => { clearTimeout(t); t = setTimeout(render, 120); });
      render();
    });
  }

  // ---------------------------------------------------------------------------------------------
  // Screen 3: one station
  // ---------------------------------------------------------------------------------------------
  function renderStation(id, seq) {
    const main = document.getElementById('app');
    if (!STATION_ID_RE.test(id)) {
      fill(main, h('h1', null, 'Unknown station'), h('p', null, h('a', { href: '#/stations' }, 'Back to all stations')), feedbackBox(null));
      return;
    }
    document.title = `FloodLead BC: ${id}`;
    const title = h('div', { class: 'hero' }, h('p', null, h('a', { href: '#/stations' }, '← All stations')), h('h1', null, id));
    const nowCard = card('Latest level', null);
    const chartCard = card('Last 7 days', null);
    const fcCard = card('FloodLead baseline forecast', null);
    fill(main, title, nowCard, chartCard, fcCard, feedbackBox(id));

    const pSt = api(`/v1/stations/${id}`);
    const pObs = api(`/v1/stations/${id}/observations?param=level&days=7`);
    const pFc = api(`/v1/stations/${id}/forecast`);

    const ctx = { model: null, chart: null };

    section(nowCard, seq, async () => {
      const st = await pSt;
      if (isStale(seq)) return;
      if (!st) { fill(title, h('p', null, h('a', { href: '#/stations' }, '← All stations')), h('h1', null, id)); fill(nowCard.body, placeholder('This station is not available.')); return; }
      document.title = `FloodLead BC: ${titleCase(st.name)}`;
      const links = st.links ? Object.entries(st.links).filter(([k, v]) => typeof v === 'string' && /^https:\/\//.test(v)) : [];
      fill(title,
        h('p', null, h('a', { href: '#/stations' }, '← All stations')),
        h('h1', null, titleCase(st.name) || id),
        h('p', { class: 'muted' }, `${st.station_id} · ${st.region || ''} · ${st.source === 'usgs' ? 'USGS' : st.source === 'eccc' ? 'Water Survey of Canada (ECCC)' : st.source || ''}`,
          links.length ? ' · ' : '', links.map(([k, v], i) => [i ? ', ' : '', extLink(v, k === 'wateroffice' ? 'Water Office' : k === 'nwps' ? 'NOAA NWPS' : k.toUpperCase())])));
      const us = isUsStation(st);
      const lv = latestOf(st);
      const cats = stationCategories(st);
      const flow = st.latest && st.latest.flow && isNum(st.latest.flow.value) ? st.latest.flow : null;
      fill(nowCard.body,
        lv ? h('div', { class: 'now-row' },
          h('span', { class: 'big' }, us ? `${fmt(mToFt(lv.value), 2)} ft` : `${fmt(lv.value, 3)} m`),
          us ? h('span', { class: 'big-m' }, `${fmt(lv.value, 2)} m`) : null) : placeholder('No recent level reading.'),
        lv ? h('p', { class: 'meta' }, 'Observed ', timeLine(lv.ts, true, snapOf(st)), ' ', provisionalTag()) : null,
        flow ? h('p', { class: 'meta' }, `Flow ${fmt(flow.value, flow.value < 10 ? 2 : 1)} m³/s, observed `, timeLine(flow.ts, false, snapOf(st))) : null,
        cats.length && lv ? stageList(cats, mToFt(lv.value), null) : null,
        cats.length ? h('p', { class: 'muted' }, `Flood stages: NOAA NWS official flood categories (${st.official_thresholds.lid || ''}).`) : h('p', { class: 'muted' }, 'No official flood thresholds are published for this gauge in FloodLead yet.'));
    });

    section(chartCard, seq, async () => {
      const [st, obs, fc] = await Promise.all([pSt, pObs, pFc]);
      if (isStale(seq)) return;
      if (!st) { fill(chartCard.body, placeholder('No data.')); return; }
      const us = isUsStation(st);
      const unit = us ? 'ft' : 'm';
      const cats = stationCategories(st);
      const models = fc && Array.isArray(fc.models) ? fc.models.filter(Boolean) : [];
      ctx.model = models.length ? models[pickModelIdx(models)] : null;
      let iss = null;
      if (fc && fc.official && Array.isArray(fc.official.points)) iss = fc.official;
      else if (st.links && st.links.nwps_lid && /^[A-Z0-9]{3,8}$/.test(st.links.nwps_lid)) iss = latestIssuance(await api(`/v1/official-forecasts/${st.links.nwps_lid}`));
      if (isStale(seq)) return;
      const pts = obsToPoints(obs && obs.observations, unit);
      const chartEl = h('div', { class: 'chart' });
      const info = h('div');
      const keyItems = [{ cls: 'sw-obs', text: `Observed (${us ? 'USGS' : 'ECCC'}, provisional)` }];
      if (iss) keyItems.push({ cls: 'sw-noaa dashed', text: `${NOAA_LABEL}, issued ${fmtPacific(iss.issued_at)}` });
      for (const c of cats) keyItems.push({ cls: `sw-${c.key} dashed`, text: `${c.name} ${us ? `${fmt(c.ft, 1)} ft` : `${fmt(c.m, 2)} m`}` });
      fill(chartCard.body, h('p', { class: 'card-sub' }, us ? 'Stage in feet (left axis) and metres (right axis, wider screens); 1 ft = 0.3048 m.' : 'Water level in metres (station datum).'), info, chartEl, legendKey(keyItems), obsSpanNote(obs, pts));
      const draw = () => {
        fill(info, ctx.model ? h('p', null, h('span', { class: 'tag tag-fl' }, `${FL_LABEL} — ${modelName(ctx.model.model)}: median and 10–90 % band`)) : null);
        removeChart(ctx.chart);
        if (isStale(seq)) return;
        ctx.chart = levelChart(chartEl, {
          unit,
          mAxis: us,
          mDecimals: 3,
          obs: pts,
          noaa: iss ? { points: noaaPoints(iss, unit), label: `NOAA NWS official forecast (unmodified), issued ${fmtPacificShort(iss.issued_at)}` } : null,
          fl: flSeries(ctx.model, unit),
          hlines: () => cats.map((c) => ({ value: us ? c.ft : c.m, color: c.color, label: `${c.name} ${us ? `${fmt(c.ft, 1)} ft` : `${fmt(c.m, 2)} m`}` })),
          vlines: () => [nowLine(snapOf(obs))],
        });
      };
      draw();
      ctx.redraw = draw;
    });

    section(fcCard, seq, async () => {
      const [st, fc] = await Promise.all([pSt, pFc]);
      if (isStale(seq)) return;
      fill(fcCard.body, chancesBlock(fc, isUsStation(st), (m) => { ctx.model = m; if (ctx.redraw) ctx.redraw(); }));
    });
  }

  // ---------------------------------------------------------------------------------------------
  // Screen 4: track record (GET /v1/track-record, one scorer run)
  // ---------------------------------------------------------------------------------------------
  function renderTrackRecord(seq) {
    const main = document.getElementById('app');
    document.title = 'FloodLead BC: track record';
    const sayCard = card('What the track record says', null);
    sayCard.classList.add('statements-card');
    const issuedCard = card('Forecasts issued and the public ledger', null);
    const skillCard = card('Skill against pure persistence', 'Pure persistence: the level now, held flat for every horizon. A forecast is only useful if it beats it.');
    fill(main,
      h('div', { class: 'hero' }, h('h1', null, 'Track record'),
        h('p', null, 'How FloodLead’s live baseline forecasts have scored so far, and how to check that none of them was changed after the outcome was known.')),
      sayCard, issuedCard, skillCard, feedbackBox(null));
    const pTr = api('/v1/track-record');
    const missing = 'The track record is not available right now. It is recomputed after every scorer run.';

    section(sayCard, seq, async () => {
      const tr = await pTr;
      if (isStale(seq)) return;
      if (!tr) { fill(sayCard.body, placeholder(missing)); return; }
      const statements = Array.isArray(tr.statements) ? tr.statements.filter((s) => typeof s === 'string' && s) : [];
      const win = tr.window || {};
      fill(sayCard.body,
        statements.length ? h('div', { class: 'statements' }, statements.map((s) => h('p', null, s))) : placeholder('No summary statements in this scorer run.'),
        h('p', { class: 'meta' }, `Scorer run ${isNum(tr.scorer_run_id) ? tr.scorer_run_id : '—'}`,
          tr.generated_at ? h('span', null, ', computed ', timeLine(tr.generated_at, false, snapOf(tr))) : null, '.'),
        win.first_base_time || win.last_valid_at ? h('p', { class: 'meta' },
          `Window: forecasts issued from ${fmtPacific(win.first_base_time)}, outcomes observed up to ${fmtPacific(win.last_valid_at)}.`,
          isNum(win.official_crossings) ? ` Official flood-stage crossings in this window: ${fmtInt(win.official_crossings)}.` : '',
          isNum(win.typical_peak_crossings) ? ` Typical-yearly-peak crossings: ${fmtInt(win.typical_peak_crossings)}.` : '') : null);
    });

    section(issuedCard, seq, async () => {
      const tr = await pTr;
      if (isStale(seq)) return;
      if (!tr) { fill(issuedCard.body, placeholder(missing)); return; }
      fill(issuedCard.body, issuedBlock(tr));
    });

    section(skillCard, seq, async () => {
      const tr = await pTr;
      if (isStale(seq)) return;
      if (!tr) { fill(skillCard.body, placeholder(missing)); return; }
      fill(skillCard.body, skillBlock(tr));
    });
  }

  function issuedBlock(tr) {
    const f = tr.forecasts || {};
    const lg = tr.ledger || {};
    const a = lg.anchor;
    const v = tr.verify || {};
    const snap = snapOf(tr);
    let anchor;
    if (a) {
      anchor = h('span', null, h('span', { class: `dot ${a.status || ''}` }), `${a.status || 'unknown'}`,
        isNum(a.seq) ? ` · seq ${fmtInt(a.seq)}` : '',
        a.anchored_at ? h('span', null, ' · anchored ', timeLine(a.anchored_at, false, snap)) : '',
        typeof a.commit_url === 'string' && /^https:\/\//.test(a.commit_url) ? h('span', null, ' · ', extLink(a.commit_url, 'commit on GitHub')) : '');
    } else {
      anchor = h('span', { class: 'muted' }, 'not anchored yet');
    }
    const cmd = (label, text) => (typeof text === 'string' && text
      ? h('div', { class: 'cmd-row' }, h('p', { class: 'cmd-label' }, label), h('div', { class: 'cmd-line' }, h('code', { class: 'cmd' }, text), copyButton(text, `Copy command: ${label}`)))
      : null);
    return h('div', null,
      h('dl', { class: 'kv' },
        h('dt', null, 'Forecasts issued'), h('dd', { class: 'num' }, fmtInt(f.issued), isNum(f.issuances) ? ` in ${fmtInt(f.issuances)} hourly issuances` : ''),
        h('dt', null, 'Since'), h('dd', null, f.first_base_time ? fmtPacific(f.first_base_time) : '—', f.last_base_time ? h('span', { class: 'muted' }, ` · latest ${fmtPacific(f.last_base_time)}`) : null),
        h('dt', null, 'Gaps'), h('dd', { class: 'num' }, isNum(f.gaps) ? `${fmtInt(f.gaps)} missed hourly issuance${f.gaps === 1 ? '' : 's'}` : '—'),
        h('dt', null, 'Chain head'), h('dd', null, isNum(lg.head_seq) ? `seq ${fmtInt(lg.head_seq)} · ` : '', hashView(lg.head_hash)),
        h('dt', null, 'Latest anchor'), h('dd', null, anchor)),
      h('h3', null, 'Verify it yourself'),
      h('p', null, 'Each command checks every entry’s hash and the links between them. Run it from a clone of the ', extLink(REPO_URL, 'source code'), '.'),
      cmd('Against the live API', v.api),
      cmd('From GitHub alone (no FloodLead server needed)', v.github),
      typeof v.spec_url === 'string' && /^https:\/\//.test(v.spec_url) ? h('p', null, extLink(v.spec_url, 'How the ledger works (ledger specification)')) : null);
  }

  function skillBlock(tr) {
    const rows = Array.isArray(tr.skill_vs_persistence) ? tr.skill_vs_persistence.filter(Boolean) : [];
    const run = isNum(tr.scorer_run_id) ? tr.scorer_run_id : '—';
    const parts = [];
    if (!rows.length) {
      parts.push(placeholder('No scored forecast–outcome pairs yet. Each horizon is scored a few hours after the forecast is issued.'));
    } else {
      const sources = Array.from(new Set(rows.map((r) => String(r.source || 'other'))))
        .sort((x, y) => (x === 'eccc' ? -1 : y === 'eccc' ? 1 : x.localeCompare(y, 'en-CA')));
      for (const src of sources) {
        const list = rows.filter((r) => String(r.source || 'other') === src)
          .sort((x, y) => String(x.model).localeCompare(String(y.model), 'en-CA') || ((isNum(x.h) ? x.h : 0) - (isNum(y.h) ? y.h : 0)));
        const skillTd = (v) => h('td', { class: `p${isNum(v) && v < 0 ? ' neg' : ''}` }, fmtSkill(v));
        const head = h('tr', null,
          h('th', null, 'Model'), h('th', { class: 'p' }, 'Horizon'), h('th', { class: 'p' }, 'n pairs'), h('th', { class: 'p' }, 'Stations'), h('th', { class: 'p' }, 'Days'),
          h('th', { class: 'p long' }, 'Fair CRPS, model (m)'), h('th', { class: 'p long' }, 'Fair CRPS, pure persistence (m)'), h('th', { class: 'p' }, 'CRPSS'),
          h('th', { class: 'p long' }, 'MAE of the median, model (m)'), h('th', { class: 'p long' }, 'MAE, pure persistence (m)'), h('th', { class: 'p' }, 'MAE skill'));
        const body = list.map((r) => h('tr', null,
          h('td', null, h('code', null, String(r.model || '—'))),
          h('td', { class: 'p' }, isNum(r.h) ? `${r.h} h` : '—'),
          h('td', { class: 'p' }, fmtInt(r.n_pairs)),
          h('td', { class: 'p' }, fmtInt(r.stations)),
          h('td', { class: 'p' }, isNum(r.days) ? fmt(r.days, Number.isInteger(r.days) ? 0 : 1) : '—'),
          h('td', { class: 'p' }, fmt(r.crps_model_m, 4)),
          h('td', { class: 'p' }, fmt(r.crps_naive_m, 4)),
          skillTd(r.crpss),
          h('td', { class: 'p' }, fmt(r.mae_model_m, 4)),
          h('td', { class: 'p' }, fmt(r.mae_naive_m, 4)),
          skillTd(r.mae_skill)));
        parts.push(
          h('h3', null, SOURCE_NAMES[src] || src),
          h('p', { class: 'table-caption' }, `Scorer run ${run}. Skill below zero means worse than pure persistence (the level now, held flat).`),
          tableBox(h('table', { class: 'skill' }, h('thead', null, head), h('tbody', null, body))));
      }
      parts.push(
        h('p', { class: 'model-explain' }, MODEL_EXPLAIN),
        h('p', { class: 'muted' }, 'Fair CRPS: the average error of the whole forecast distribution, in metres (lower is better). MAE of the median: the average distance between the middle forecast and what happened. CRPSS and MAE skill = 1 − model ÷ pure persistence, on the same forecast–outcome pairs; n pairs, stations and days say how much data each row rests on.'));
    }
    parts.push(
      h('h3', null, 'Against NOAA’s official forecasts'),
      h('p', null, 'Matched forecast–outcome pairs (FloodLead and NOAA NWS for the same Nooksack gauge, base time and horizon): ',
        h('strong', { class: 'num' }, fmtInt(tr.noaa_matched_pairs)), ` (scorer run ${run}). Details: `,
        h('a', { href: '/v1/scores/official' }, '/v1/scores/official'), ' (JSON).'));
    return h('div', null, parts);
  }

  // ---------------------------------------------------------------------------------------------
  // Footer: data feed status
  // ---------------------------------------------------------------------------------------------
  async function renderHealth() {
    const el = document.getElementById('health-line');
    if (!el) return;
    try {
      const hl = await api('/v1/health');
      if (!hl) { fill(el, 'Data feed status unavailable'); return; }
      const names = { eccc: 'ECCC', usgs: 'USGS', nwps: 'NOAA NWS' };
      const src = hl.sources || {};
      fill(el, 'Data feeds: ', Object.keys(names).filter((k) => src[k]).map((k, i) => [
        i ? ', ' : '', h('span', { class: `dot ${src[k].status || ''}` }), `${names[k]} ${src[k].status || '?'}`,
        isNum(src[k].lag_min) ? ` (newest data ${fmtDuration(src[k].lag_min)} old)` : '']),
      hl.generated_at ? ` · checked ${fmtPacific(hl.generated_at)}` : '');
    } catch (e) {
      fill(el, 'Data feed status unavailable');
    }
  }

  // ---------------------------------------------------------------------------------------------
  // Router
  // ---------------------------------------------------------------------------------------------
  function route() {
    const seq = ++state.renderSeq;
    destroyCharts();
    const hash = location.hash || '#/';
    let name = 'watch';
    try {
      if (hash.startsWith('#/station/')) {
        name = 'stations';
        renderStation(decodeURIComponent(hash.slice('#/station/'.length)), seq);
        try { window.scrollTo(0, 0); } catch (e) { /* not available */ }
      } else if (hash.startsWith('#/stations')) {
        name = 'stations';
        renderStations(seq);
      } else if (hash.startsWith('#/track-record')) {
        name = 'track';
        renderTrackRecord(seq);
        try { window.scrollTo(0, 0); } catch (e) { /* not available */ }
      } else {
        renderWatch(seq);
      }
    } catch (err) {
      console.error(err);
      fill(document.getElementById('app'), placeholder('Something went wrong while drawing this page. Please reload.'));
    }
    for (const a of document.querySelectorAll('.nav a')) a.classList.toggle('active', a.dataset.route === name);
  }

  function start() {
    window.addEventListener('hashchange', route);
    window.addEventListener('unhandledrejection', (e) => { console.error('Unhandled:', e.reason); });
    setInterval(updateAges, 30000);
    route();
    renderHealth();
  }

  // Exposed for the backend's snapshot exporter, tests and debugging.
  window.FloodLead = { snapshotSlug, pExceedFromQuantiles, api };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
