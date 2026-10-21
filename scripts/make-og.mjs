// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
// Render the 1200x630 social card (site/img/og.jpg) from brand/gryvia-icon.svg and brand/tokens.json.
//   node scripts/make-og.mjs
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(fileURLToPath(import.meta.url), '..', '..');
const icon = 'data:image/svg+xml;base64,' + readFileSync(join(root, 'brand/gryvia-icon.svg')).toString('base64');
const accent = JSON.parse(readFileSync(join(root, 'brand/tokens.json'), 'utf8')).accent;
const cells = Array.from({ length: 24 }, (_, i) => `<i class="${i < 13 ? 'on' : ''}"></i>`).join('');
const html = `<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}
body{width:1200px;height:630px;background:radial-gradient(900px 520px at 85% -10%,${accent}55,transparent 70%),#05070b;color:#f5f5f7;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;padding:76px 86px;position:relative;overflow:hidden}
img{width:150px;height:150px;display:block}
h1{font-size:92px;line-height:1.05;letter-spacing:-.025em;margin-top:40px;font-weight:700;white-space:nowrap}
p{font-size:32px;line-height:1.4;color:#a1a1a8;margin-top:22px;max-width:760px}
small{position:absolute;left:86px;bottom:56px;font-size:23px;color:#76767e}
.grid{position:absolute;right:86px;top:96px;display:grid;grid-template-columns:repeat(6,28px);gap:10px}
.grid i{width:28px;height:28px;border-radius:7px;background:#2a2d34;display:block}
.grid i.on{background:${accent};box-shadow:0 0 18px ${accent}99}
</style><img src="${icon}"><div class="grid">${cells}</div>
<h1>Your Macs, scheduled.</h1>
<p>A multi-tenant control plane for Apple Silicon fleets. Admission · quotas · live GPUs · provenance.</p>
<small>Zyvor AI Labs · source-available (BUSL-1.1)</small>`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
await page.setContent(html);
await page.screenshot({ path: join(root, 'site/img/og.jpg'), type: 'jpeg', quality: 90 });
await browser.close();
console.log('wrote site/img/og.jpg');
