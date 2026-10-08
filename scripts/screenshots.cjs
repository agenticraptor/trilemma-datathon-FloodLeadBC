// Screenshots of the demo path with headless Chromium (Puppeteer). Reproduce with:
//   docker run --rm -e NODE_PATH=/usr/src/app/node_modules -v "$PWD/scripts:/s:ro" -v "<writable dir>:/out" \
//     zenika/alpine-chrome@sha256:ee10e24217aa27443e6b58da628f3b09ea9b814459915b8b62fe15a555f9692a \
//     node /s/screenshots.cjs https://<PUBLIC_HOSTNAME>/ /out [personal_level_ft]
// (add `--network host` and use http://localhost:8080/ to check a local static server, i.e. snapshot mode)
// Writes PNGs plus
//   console-errors.txt  console errors, page errors and failed requests per page, and a page-error count;
//   layout-check.txt    per page and width: document.documentElement.scrollWidth vs the viewport width,
//                       and when the page is wider than the viewport, every element wider than it
//                       (tag, class, width). Also one load with navigator.language = 'en-US@posix'.
// Locale: Chromium runs with --lang=en-CA, the CDP locale override en-CA, and Accept-Language: en-CA.
const puppeteer = require('puppeteer');
const fs = require('fs');

const base = process.argv[2];
const out = process.argv[3];
const personal = process.argv[4] || '147.0';

(async () => {
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium-browser',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--lang=en-CA'] });
  const log = [];
  const layout = [];
  let pageErrors = 0;
  async function open(name, width, hash, before) {
    const page = await browser.newPage();
    page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) log.push(`${name}: console.${m.type()}: ${m.text()}`); });
    page.on('pageerror', (e) => { pageErrors += 1; log.push(`${name}: pageerror: ${e.message}`); });
    page.on('requestfailed', (r) => log.push(`${name}: requestfailed: ${r.url()} ${r.failure() && r.failure().errorText}`));
    await page.setExtraHTTPHeaders({ 'Accept-Language': 'en-CA,en;q=0.9' });
    try { const cdp = await page.target().createCDPSession(); await cdp.send('Emulation.setLocaleOverride', { locale: 'en-CA' }); } catch (e) { log.push(`${name}: locale override failed: ${e.message}`); }
    await page.evaluateOnNewDocument((v) => { try { localStorage.setItem('floodlead.personalLevelFt.v1', v); } catch (e) {} }, personal);
    if (before) await page.evaluateOnNewDocument(before);
    await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
    await page.goto(base + hash, { waitUntil: 'networkidle0', timeout: 90000 });
    await new Promise((r) => setTimeout(r, 2000));
    await checkLayout(page, name, hash);
    return page;
  }
  async function checkLayout(page, name, hash) {
    const r = await page.evaluate(() => {
      const vw = window.innerWidth;
      const sw = document.documentElement.scrollWidth;
      const wide = [];
      if (sw > vw) {
        for (const el of document.querySelectorAll('body *')) {
          const b = el.getBoundingClientRect();
          if (b.width > vw || b.right > vw + 0.5) {
            wide.push(`${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : ''} width=${Math.round(b.width)} right=${Math.round(b.right)}`);
          }
        }
      }
      const legends = [...document.querySelectorAll('.u-legend')].map((l) => Math.round(l.getBoundingClientRect().width));
      return { vw, sw, wide, legends, charts: document.querySelectorAll('.uplot').length,
        lang: navigator.language, banner: (document.getElementById('snapshot-banner') || {}).hidden === false
          ? document.getElementById('snapshot-banner').textContent : '',
        ages: [...document.querySelectorAll('.age')].slice(0, 4).map((a) => a.textContent) };
    });
    layout.push(`${name} ${hash}: scrollWidth=${r.sw} viewport=${r.vw} ${r.sw <= r.vw ? 'OK' : 'OVERFLOW'}`
      + ` · charts=${r.charts} legendWidths=[${r.legends.join(',')}] · navigator.language=${r.lang}`
      + (r.banner ? ` · banner="${r.banner}"` : '') + (r.ages.length ? ` · ages=${JSON.stringify(r.ages)}` : ''));
    for (const w of r.wide.slice(0, 40)) layout.push(`    wider than viewport: ${w}`);
  }
  async function card(page, file, match) {
    const el = await page.evaluateHandle((m) => [...document.querySelectorAll('section.card')]
      .find((s) => (s.querySelector('h2') || {}).textContent && s.querySelector('h2').textContent.toLowerCase().includes(m)), match);
    if (el && el.asElement()) await el.asElement().screenshot({ path: `${out}/${file}.png` });
    else log.push(`${file}: no card matching "${match}"`);
  }
  for (const [tag, width] of [['desktop', 1280], ['375px', 375]]) {
    const p = await open(`watch-${tag}`, width, '#/');
    await p.screenshot({ path: `${out}/overflow-watch-${tag}-full.png`, fullPage: true });
    await card(p, `live-view-${tag}`, 'now at');
    await card(p, `chart-${tag}`, 'last 7 days');
    await card(p, `personal-level-${tag}`, 'own level');
    await card(p, `replay-${tag}`, 'replay');
    await card(p, `chances-${tag}`, 'chance');
    await card(p, `ledger-${tag}`, 'ledger');
    await p.close();
    const l = await open(`stations-${tag}`, width, '#/stations');
    await l.screenshot({ path: `${out}/stations-${tag}.png` });
    await l.close();
    const s = await open(`station-${tag}`, width, '#/station/eccc:08MH001');
    await s.screenshot({ path: `${out}/station-08MH001-${tag}.png`, fullPage: true });
    await s.close();
    const u = await open(`station-usgs-${tag}`, width, '#/station/usgs:12210700');
    await u.screenshot({ path: `${out}/station-12210700-${tag}.png`, fullPage: true });
    await u.close();
  }
  // A browser whose default locale is POSIX reports navigator.language = 'en-US@posix' (not a valid
  // BCP 47 tag). The page must still load with 0 page errors and draw its charts.
  const before = pageErrors;
  const px = await open('posix-locale', 1280, '#/', () => {
    Object.defineProperty(navigator, 'language', { get: () => 'en-US@posix' });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US@posix'] });
  });
  await px.screenshot({ path: `${out}/posix-locale-desktop.png` });
  await px.close();
  layout.push(`posix-locale: page errors=${pageErrors - before}`);
  log.push(`page errors (all pages): ${pageErrors}; with navigator.language=en-US@posix: ${pageErrors - before}`);
  fs.writeFileSync(`${out}/console-errors.txt`, (log.join('\n') || 'none') + '\n');
  fs.writeFileSync(`${out}/layout-check.txt`, layout.join('\n') + '\n');
  await browser.close();
})();
