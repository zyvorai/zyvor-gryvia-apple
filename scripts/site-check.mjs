// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
// Serve _site/ and check it: loads, no console errors, no horizontal scroll at phone width, light and dark, demo boots.
//   node scripts/site-check.mjs [--shots DIR]
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(fileURLToPath(import.meta.url), '..', '..', '_site');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.xml': 'application/xml', '.txt': 'text/plain' };
const server = createServer(async (req, res) => {
  let p = normalize(req.url.split('?')[0]); if (p.endsWith('/')) p += 'index.html';
  try { const d = await readFile(join(root, p)); res.writeHead(200, { 'content-type': types[extname(p)] || 'application/octet-stream' }); res.end(d); }
  catch { res.writeHead(404); res.end('nf'); }
}).listen(0);
await new Promise(r => server.once('listening', r));
const base = `http://127.0.0.1:${server.address().port}/`;
const shotsDir = process.argv.includes('--shots') ? process.argv[process.argv.indexOf('--shots') + 1] : null;
const browser = await chromium.launch();
const problems = [];
for (const [name, size, scheme] of [['desktop-light', { width: 1440, height: 900 }, 'light'], ['desktop-dark', { width: 1440, height: 900 }, 'dark'], ['phone', { width: 390, height: 844 }, 'light']]) {
  const ctx = await browser.newContext({ viewport: size, colorScheme: scheme });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('requestfailed', r => errs.push('request failed: ' + r.url()));
  const resp = await page.goto(base, { waitUntil: 'load' });
  if (!resp || resp.status() !== 200) problems.push(`${name}: status ${resp && resp.status()}`);
  const h1 = await page.textContent('h1');
  if (!/scheduled/i.test(h1)) problems.push(`${name}: hero headline missing`);
  if (name === 'desktop-light') {
    const body = await page.textContent('body');
    for (const price of ['₹420', '₹4,999', '₹19,999']) if (!body.includes(price)) problems.push(`plan price text missing: ${price}`);
    const buy = await page.getAttribute('a:has-text("Buy Personal")', 'href');
    if (!buy || !/^https:\/\//.test(buy)) problems.push(`buy link missing or not https: ${buy}`);
    const invoice = await page.getAttribute('a:has-text("Request an invoice")', 'href');
    if (!invoice || !/^mailto:sales@zyvor\.dev/.test(invoice)) problems.push(`invoice link missing or wrong: ${invoice}`);
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  if (overflow) problems.push(`${name}: horizontal scroll`);
  const imgs = await page.evaluate(() => [...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.src));
  if (imgs.length) problems.push(`${name}: broken images ${imgs.join(', ')}`);
  if (name === 'desktop-light') {
    await page.click('[role=tab][data-variant=dark]');
    if (await page.locator('[data-variant=dark]:not([role=tab])').first().isHidden()) problems.push('screenshot tabs do not switch');
    const hasOg = await page.getAttribute('meta[property="og:image"]', 'content');
    if (!hasOg) problems.push('og:image missing');
  }
  await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); } window.scrollTo(0, 0); });
  // feature walkthrough and spec strip
  const w = await page.evaluate(() => ({
    steps: document.querySelectorAll('#story-root .step').length,
    focusable: [...document.querySelectorAll('#story-root .step')].every(s => s.tabIndex === 0),
    current: document.querySelectorAll('#story-root .step[aria-current]').length,
    specs: document.querySelectorAll('#specs .spec').length,
    specText: document.querySelector('#specs')?.textContent || '',
    stageShown: !!document.querySelector('.story-stage') && getComputedStyle(document.querySelector('.story-stage')).display !== 'none',
    inlineShown: getComputedStyle(document.querySelector('.step-img')).display !== 'none',
  }));
  if (w.steps !== 5 || !w.focusable) problems.push(`${name}: walkthrough needs 5 focusable steps`);
  if (w.current !== 1) problems.push(`${name}: exactly one step must have aria-current (got ${w.current})`);
  if (w.specs !== 4 || !/TEST_RESULTS\.md/.test(w.specText) || !/not per job/i.test(w.specText) || !/simulated/i.test(w.specText)) problems.push(`${name}: spec strip incomplete`);
  if (/\b(first|only)\b/i.test(w.specText)) problems.push(`${name}: spec strip must not claim "first" or "only"`);
  if (name === 'phone' ? (w.stageShown || !w.inlineShown) : (!w.stageShown || w.inlineShown)) problems.push(`${name}: walkthrough layout (stage ${w.stageShown}, inline ${w.inlineShown})`);
  const unloaded = await page.evaluate(() => [...document.querySelectorAll('#story img, #specs img')].filter(i => i.offsetParent !== null && i.getBoundingClientRect().width > 0 && i.naturalWidth === 0).map(i => i.src));
  if (unloaded.length) problems.push(`${name}: visible walkthrough images not loaded ${unloaded.join(', ')}`);
  const contrast = await page.evaluate(() => {
    const lum = c => { const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); return .2126 * r + .7152 * g + .0722 * b; };
    const el = document.querySelector('.btn.primary'), cs = getComputedStyle(el), [a, b] = [lum(cs.color), lum(cs.backgroundColor)].sort((x, y) => y - x);
    return (a + .05) / (b + .05);
  });
  if (contrast < 4.5) problems.push(`${name}: .btn.primary contrast ${contrast.toFixed(2)} < 4.5`);
  if (name === 'desktop-light') {
    await page.locator('#story-root .step').first().focus();
    await page.keyboard.press('ArrowDown');
    await page.waitForTimeout(300);
    const cur = await page.evaluate(() => ({ step: document.querySelector('#story-root .step[aria-current]')?.dataset.step, shot: document.querySelector('.stage-imgs .shot.on')?.dataset.step, w: document.querySelector('.stage-imgs .shot.on img.light')?.naturalWidth }));
    if (cur.step !== '1' || cur.shot !== '1') problems.push(`walkthrough arrow key did not advance (${JSON.stringify(cur)})`);
    if (!(cur.w > 0)) problems.push('walkthrough stage image did not load after swap');
  }
  if (shotsDir) await page.screenshot({ path: join(shotsDir, `site-${name}.png`), fullPage: true });
  if (errs.length) problems.push(`${name}: ${errs.join(' | ')}`);
  await ctx.close();
}
// reduced motion and no JavaScript: the new sections are fully visible
for (const [label, opts] of [['reduced-motion', { reducedMotion: 'reduce' }], ['no-js', { javaScriptEnabled: false }]]) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, ...opts });
  const page = await ctx.newPage();
  await page.goto(base, { waitUntil: 'load' });
  const hidden = await page.evaluate(() => [...document.querySelectorAll('#story .step, #specs .spec, #specs .reveal')].filter(e => parseFloat(getComputedStyle(e).opacity) < 0.99).length);
  if (hidden) problems.push(`${label}: ${hidden} walkthrough/spec elements are not fully visible`);
  if (label === 'no-js' && !(await page.evaluate(() => getComputedStyle(document.querySelector('.step-img')).display !== 'none'))) problems.push('no-js: step images not shown');
  if (shotsDir) await page.screenshot({ path: join(shotsDir, `site-${label}.png`), fullPage: true });
  await ctx.close();
}
// the demo boots and shows the simulated-fleet banner
{
  const page = await browser.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  await page.goto(base + 'demo/');
  await page.click('#demo-start');
  await page.waitForSelector('#gpu-cards .gpu-card');
  if (await page.locator('#demo-banner').isHidden()) problems.push('demo banner (simulated fleet) not shown');
  if (errs.length) problems.push('demo: ' + errs.join(' | '));
}
await browser.close(); server.close();
if (problems.length) { console.error('site-check FAILED:\n  ' + problems.join('\n  ')); process.exit(1); }
console.log('site-check ok');
