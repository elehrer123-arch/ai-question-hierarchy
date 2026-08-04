#!/usr/bin/env node
/**
 * Smoke + accessibility checks for the built site.
 *   node scripts/smoke.js [rootDir]
 * Exits non-zero on failure. Run after `python3 scripts/build.py`.
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const ROOT = path.resolve(process.argv[2] || '.');
const url = (p) => 'file://' + path.join(ROOT, p);
const fails = [];
const ok = (cond, msg) => { if (!cond) fails.push(msg); };

(async () => {
  const exe = process.env.PW_CHROMIUM === undefined
    ? '/opt/pw-browsers/chromium'
    : (process.env.PW_CHROMIUM || undefined);
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  const consoleErrors = [];
  page.on('pageerror', (e) => consoleErrors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });

  // pick a question page that exists
  const qdirs = fs.readdirSync(path.join(ROOT, 'questions')).filter((d) =>
    fs.existsSync(path.join(ROOT, 'questions', d, 'index.html')));
  ok(qdirs.length >= 100, `expected 100+ question pages, found ${qdirs.length}`);
  const qslug = qdirs.includes('containment-control') ? 'containment-control' : qdirs[0];

  const PAGES = [
    ['index.html', 'map'],
    ['browse/index.html', 'browse'],
    ['latest/index.html', 'latest'],
    ['methodology/index.html', 'methodology'],
    ['poster/index.html', 'poster'],
    [`questions/${qslug}/index.html`, 'question page'],
  ];

  for (const [p, label] of PAGES) {
    consoleErrors.length = 0;
    await page.goto(url(p));
    await page.waitForTimeout(350);
    const a = await page.evaluate(() => {
      const imgs = [...document.querySelectorAll('img')].filter((i) => !i.hasAttribute('alt'));
      const h1 = document.querySelectorAll('h1').length;
      const btns = [...document.querySelectorAll('button')].filter(
        (b) => !b.textContent.trim() && !b.getAttribute('aria-label'));
      const links = [...document.querySelectorAll('a[href]')].filter(
        (l) => !l.textContent.trim() && !l.getAttribute('aria-label') && !l.querySelector('svg,img'));
      const nested = document.querySelectorAll('button a, a button, button button').length;
      const anchors = [...document.querySelectorAll('a[href]')];
      const isExt = (a) => { try { const u = new URL(a.href, location.href);
        return (u.protocol === 'http:' || u.protocol === 'https:') && u.host !== location.host;
      } catch (e) { return false; } };
      const ext = anchors.filter(isExt);
      const extNotBlank = ext.filter((a) => a.target !== '_blank').length;
      const extNoRel = ext.filter((a) => !/noopener/.test(a.rel)).length;
      const intBlank = anchors.filter((a) => !isExt(a) && a.target === '_blank').length;
      return { imgsNoAlt: imgs.length, h1, unlabeledButtons: btns.length,
               emptyLinks: links.length, nestedInteractive: nested, title: document.title,
               extNotBlank, extNoRel, intBlank };
    });
    ok(consoleErrors.length === 0, `${label}: console errors — ${consoleErrors.join(' | ')}`);
    ok(a.title && a.title.length > 5, `${label}: missing/short <title>`);
    ok(a.h1 === 1, `${label}: expected exactly one <h1>, found ${a.h1}`);
    ok(a.imgsNoAlt === 0, `${label}: ${a.imgsNoAlt} <img> without alt`);
    ok(a.unlabeledButtons === 0, `${label}: ${a.unlabeledButtons} unlabeled buttons`);
    ok(a.emptyLinks === 0, `${label}: ${a.emptyLinks} links with no accessible text`);
    ok(a.nestedInteractive === 0, `${label}: ${a.nestedInteractive} nested interactive elements`);
    ok(a.extNotBlank === 0, `${label}: ${a.extNotBlank} external links not opening in a new tab`);
    ok(a.extNoRel === 0, `${label}: ${a.extNoRel} external links missing rel=noopener`);
    ok(a.intBlank === 0, `${label}: ${a.intBlank} internal links wrongly opening in a new tab`);
  }

  // keyboard: tab reaches the map search box
  await page.goto(url('index.html'));
  await page.waitForTimeout(250);
  let reached = false;
  for (let i = 0; i < 12 && !reached; i++) {
    await page.keyboard.press('Tab');
    reached = await page.evaluate(() => document.activeElement?.id === 'mapsearch');
  }
  ok(reached, 'map: search box not reachable within 12 tab stops');

  // map volume toggle exposes real links
  await page.click('#voltoggle');
  await page.waitForTimeout(200);
  const vol = await page.evaluate(() => {
    const v = document.querySelector('.vol');
    return { tag: v?.tagName, href: v?.getAttribute('href') };
  });
  ok(vol.tag === 'A' && /latest\/\?q=/.test(vol.href || ''), 'map: volume count is not a real link');

  // map: a question expands and its question-page link navigates
  await page.goto(url('index.html'));
  await page.waitForTimeout(300);
  await page.click('.bqhead');
  await page.waitForTimeout(400);
  const opened = await page.evaluate(() => document.querySelectorAll('.bq.open').length);
  ok(opened === 1, `map: clicking a question did not expand it (${opened} open)`);
  const qlink = await page.evaluate(() => {
    const a = document.querySelector('.bq.open a.bopen[href^="questions/"]');
    if (!a) return null;
    const r = a.getBoundingClientRect();
    return { href: a.getAttribute('href'), visible: r.width > 0 && r.height > 0 };
  });
  ok(qlink && qlink.visible, 'map: expanded question exposes no visible question-page link');
  if (qlink) {
    await page.click('.bq.open a.bopen[href^="questions/"]');
    await page.waitForTimeout(500);
    ok(/\/questions\/[^/]+\/?$/.test(page.url()),
       `map: question-page link did not navigate (landed on ${page.url()})`);
    await page.goBack();
    await page.waitForTimeout(300);
  }

  // map: the recently-tracked rail navigates too
  await page.goto(url('index.html'));
  await page.waitForTimeout(300);
  const railHref = await page.evaluate(() =>
    document.querySelector('.recit')?.getAttribute('href') || null);
  ok(railHref && railHref.startsWith('questions/'),
     `map: recent rail link missing or not a question page (${railHref})`);

  // latest deep link + filters
  await page.goto(url('latest/index.html') + '?q=2.4.4&featured=1');
  await page.waitForTimeout(350);
  const lat = await page.evaluate(() => {
    const vis = [...document.querySelectorAll('.li')].filter((l) => l.style.display !== 'none');
    return { visible: vis.length, allSameQ: vis.every((l) => l.dataset.q === '2.4.4'),
             noLedger: vis.every((l) => !l.classList.contains('lg')),
             pill: document.getElementById('qpill')?.classList.contains('on') };
  });
  ok(lat.visible > 0, 'latest: deep link ?q=2.4.4 shows nothing');
  ok(lat.allSameQ, 'latest: deep link leaked other questions');
  ok(lat.noLedger, 'latest: featured=1 still shows ledger items');
  ok(lat.pill, 'latest: question pill not shown for deep link');

  // browse back-button history
  await page.goto(url('browse/index.html') + '#q1-1-1');
  await page.reload();
  await page.waitForTimeout(350);
  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.trow')].find((r) => r.dataset.k === '2.1.1');
    if (t) t.click();
  });
  await page.waitForTimeout(300);
  await page.goBack();
  await page.waitForTimeout(300);
  const back = await page.evaluate(() => location.hash);
  ok(back === '#1-1-1' || back === '#q1-1-1', `browse: Back did not restore prior question (hash ${back})`);

  // evidence anchors resolve
  await page.goto(url(`questions/${qslug}/index.html`));
  const ev = await page.evaluate(() => {
    const links = [...document.querySelectorAll('.evd a')];
    return { n: links.length,
             allResolve: links.every((l) => !!document.querySelector(l.getAttribute('href'))) };
  });
  ok(ev.n === 0 || ev.allResolve, 'question page: evidence anchors do not resolve to items');

  await browser.close();
  if (fails.length) {
    console.error('SMOKE FAILURES:\n - ' + fails.join('\n - '));
    process.exit(1);
  }
  console.log(`smoke: OK (${PAGES.length} pages, ${qdirs.length} question pages, a11y + keyboard + deep links + history + evidence anchors)`);
})();
