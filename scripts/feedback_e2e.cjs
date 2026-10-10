// End-to-end check of the in-app feedback box on the public URL (Stage 3, AC-2), with headless Chromium (Puppeteer).
// It submits ONE synthetic item (no personal data) from #/track-record and screenshots the form before and after.
// Reproduce: docker run --rm -e NODE_PATH=/usr/src/app/node_modules -v "$PWD/scripts:/s:ro" -v "<dir>:/out" \
//   zenika/alpine-chrome@sha256:ee10e24217aa27443e6b58da628f3b09ea9b814459915b8b62fe15a555f9692a \
//   node /s/feedback_e2e.cjs https://<PUBLIC_HOSTNAME>/ /out
const puppeteer = require('puppeteer');

const base = process.argv[2];
const out = process.argv[3];
const TEXT = 'Synthetic end-to-end test by the build worker (no personal data).';

(async () => {
  const browser = await puppeteer.launch({ args: ['--no-sandbox', '--lang=en-CA'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 375, height: 900, deviceScaleFactor: 2 });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  let posted = null;
  page.on('response', (r) => { if (r.url().endsWith('/v1/feedback')) posted = r.status(); });
  await page.goto(`${base}#/track-record`, { waitUntil: 'networkidle0' });
  const form = await page.waitForSelector('section.card.feedback');
  await form.scrollIntoView();
  const [yes] = await page.$$('section.card.feedback .tabs button');
  await yes.click();
  await page.type('#fb-text', TEXT);
  await form.screenshot({ path: `${out}/feedback-before-submit-375.png` });
  await page.click('section.card.feedback button[type=submit]');
  await page.waitForFunction(() => /Thank you|could not|Too many/.test(
    document.querySelector('section.card.feedback .fb-status')?.textContent || ''), { timeout: 15000 });
  const status = await page.$eval('section.card.feedback .fb-status', (e) => e.textContent);
  await form.screenshot({ path: `${out}/feedback-after-submit-375.png` });
  console.log(JSON.stringify({ http_status: posted, status_text: status, page_errors: errors }));
  await browser.close();
})();
