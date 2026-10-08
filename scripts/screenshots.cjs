// Screenshots of the demo path with headless Chromium (Puppeteer). Reproduce with:
//   docker run --rm -e NODE_PATH=/usr/src/app/node_modules -v "$PWD/scripts:/s:ro" -v "<writable dir>:/out" \
//     zenika/alpine-chrome@sha256:ee10e24217aa27443e6b58da628f3b09ea9b814459915b8b62fe15a555f9692a \
//     node /s/screenshots.cjs https://<PUBLIC_HOSTNAME>/ /out [personal_level_ft]
// Writes PNGs plus console-errors.txt (console errors, page errors and failed requests per screenshot).
const puppeteer = require('puppeteer');
const fs = require('fs');

const base = process.argv[2];
const out = process.argv[3];
const personal = process.argv[4] || '146.2';

(async () => {
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium-browser',
    args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const log = [];
  async function open(name, width, hash) {
    const page = await browser.newPage();
    page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) log.push(`${name}: console.${m.type()}: ${m.text()}`); });
    page.on('pageerror', (e) => log.push(`${name}: pageerror: ${e.message}`));
    page.on('requestfailed', (r) => log.push(`${name}: requestfailed: ${r.url()} ${r.failure() && r.failure().errorText}`));
    await page.evaluateOnNewDocument((v) => { try { localStorage.setItem('floodlead.personalLevelFt.v1', v); } catch (e) {} }, personal);
    await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
    await page.goto(base + hash, { waitUntil: 'networkidle0', timeout: 90000 });
    await new Promise((r) => setTimeout(r, 2000));
    return page;
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
    await card(p, `personal-level-${tag}`, 'own level');
    await card(p, `replay-${tag}`, 'replay');
    await card(p, `chances-${tag}`, 'chance');
    await card(p, `ledger-${tag}`, 'ledger');
    await p.close();
    const s = await open(`station-${tag}`, width, '#/station/eccc:08MH001');
    await s.screenshot({ path: `${out}/station-08MH001-${tag}.png`, fullPage: true });
    await s.close();
  }
  fs.writeFileSync(`${out}/console-errors.txt`, (log.join('\n') || 'none') + '\n');
  await browser.close();
})();
