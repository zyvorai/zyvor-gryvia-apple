// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
// Every view at desktop and phone width, light and dark: no horizontal page scroll, and no axe-core WCAG 2.x A/AA violations.
const {chromium}=require('playwright');const axeSource=require('fs').readFileSync(require.resolve('axe-core/axe.min.js'),'utf8');
const VIEWS=['guide','live','overview','fleet','timeline','models','datasets','training','playground','jobs','workflows','deployments','tenants','alerts','audit','settings'];
const SIZES=[[1440,900,'light'],[390,844,'light'],[1440,900,'dark'],[390,844,'dark']];
(async()=>{const browser=await chromium.launch({headless:true});const problems=[];
for(const [width,height,scheme] of SIZES){
  const page=await browser.newPage({viewport:{width,height},colorScheme:scheme});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765');await page.fill('#token','browser-test-admin-token-00000000');await page.click('#login button');await page.waitForSelector('#hero .num');
  for(const view of VIEWS){
    await page.evaluate(v=>{const b=document.querySelector(`[data-view="${v}"]`);b&&b.click()},view);await page.waitForTimeout(250);
    const over=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
    if(over>1)problems.push(`${view} @${width}px ${scheme}: page scrolls horizontally by ${over}px`);
    await page.evaluate(axeSource);
    const res=await page.evaluate(()=>axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa']},resultTypes:['violations']}));
    for(const v of res.violations)problems.push(`${view} @${width}px ${scheme}: ${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes[0].target.join(' ')}`);
  }
  errors.forEach(e=>problems.push('JS error: '+e));await page.close();
}
await browser.close();
if(problems.length){console.error(problems.join('\n'));process.exit(1)}
console.log(`PASS: ${VIEWS.length} views x ${SIZES.length} width/scheme combinations: no horizontal scroll, no axe WCAG A/AA violations`);})().catch(e=>{console.error(e);process.exit(1)});
