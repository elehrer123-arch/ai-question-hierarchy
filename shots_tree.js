const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1200 } });
  const errs=[]; page.on('pageerror',e=>errs.push(e.message));
  for (const v of ['radial','orchard','regions','broadsheet']) {
    await page.goto(`file:///home/claude/work/push/preview/tree/${v}/index.html`);
    await page.waitForTimeout(200);
    await page.screenshot({ path: `tree_${v}.png`, fullPage: v!=='radial' });
  }
  console.log('errors:', errs.length?errs:'none');
  await browser.close();
})();
