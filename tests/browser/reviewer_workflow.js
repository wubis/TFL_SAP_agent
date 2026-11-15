// Drives the reviewer page in a real browser: two corrections, an application restart, export, then scoring.
// Usage: node reviewer_workflow.js <phase: correct|verify> <base url> <output folder>
const { chromium } = require('playwright');
const fs = require('fs');

async function selectAndCite(page, phrase) {
  const cited = await page.evaluate((phrase) => {
    for (const node of document.querySelectorAll('#source-pane .card .text')) {
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      let text;
      while ((text = walker.nextNode())) {
        const at = text.data.indexOf(phrase);
        if (at === -1) continue;
        const range = document.createRange();
        range.setStart(text, at); range.setEnd(text, at + phrase.length);
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        node.parentElement.querySelector('button').click();
        return node.parentElement.querySelector('.meta').textContent;
      }
    }
    return null;
  }, phrase);
  if (!cited) throw new Error('Phrase not found in any passage shown: ' + phrase);
  return cited;
}
async function openComponent(page, shellText, label, kind) {
  const option = page.locator('#shell option', { hasText: shellText }).first();
  await page.locator('#shell').selectOption(await option.getAttribute('value'));
  await page.locator('ul.components li', { hasText: label }).filter({ hasText: kind }).first().click();
}

(async () => {
  const [phase, base, out] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 }, deviceScaleFactor: 1, acceptDownloads: true });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(base + '/');
  await page.waitForSelector('ul.components li');

  if (phase === 'correct') {
    // Correction 1: the table's population label, supported by the definition and the section that applies it.
    await openComponent(page, 'FEV1 summary by visit', 'Full Analysis Set', 'population label');
    await page.getByRole('button', { name: 'Correct', exact: true }).click();
    console.log('cited:', await selectAndCite(page, 'have at least one post-baseline blood eosinophils count assessment (Day 2)'));
    console.log('cited:', await selectAndCite(page, 'The analysis of the secondary efficacy endpoints will be carried out for the FAS population.'));
    await page.locator('#correction select').selectOption('supported');
    await page.locator('#correction textarea').nth(0).fill('Section 5.3 defines the Full Analysis Set. Section 17.2.1.1 applies it to the secondary efficacy endpoints, which include FEV1.');
    await page.locator('#correction textarea').nth(1).fill('');
    await page.locator('#note').fill('Corrected in the browser workflow check.');
    await page.getByRole('button', { name: 'Save correction' }).click();
    await page.waitForFunction(() => document.getElementById('summary').textContent.includes('1 corrected'));

    // Correction 2: the listing's population label, citing a passage found by searching the whole SAP.
    await openComponent(page, 'Subject-level spirometry', 'Full Analysis Set', 'population label');
    await page.getByRole('button', { name: 'Correct', exact: true }).click();
    await page.locator('#query').fill('listings patients analysis sets');
    await page.getByRole('button', { name: 'Search' }).click();
    await page.waitForFunction(() => [...document.querySelectorAll('#source-pane .meta')].some(node => node.textContent.startsWith('Search result')));
    const found = await page.evaluate(() => {
      const candidates = new Set([...document.querySelectorAll('#source-pane .card')].filter(card => card.querySelector('.meta').textContent.startsWith('Rank')).map(card => card.querySelector('.text').textContent));
      const card = [...document.querySelectorAll('#source-pane .card')].find(card => card.querySelector('.meta').textContent.startsWith('Search result') && !candidates.has(card.querySelector('.text').textContent));
      return card.querySelector('.text').textContent.split(' ').slice(0, 10).join(' ');
    });
    console.log('cited from search:', await selectAndCite(page, found));
    await page.locator('#correction select').selectOption('needs_review');
    await page.locator('#correction textarea').nth(0).fill('The title says Full Analysis Set. A passage found by search may set a different scope for listings.');
    await page.locator('#correction textarea').nth(1).fill('Does this listing follow the Full Analysis Set or the general listing rule?');
    await page.getByRole('button', { name: 'Save correction' }).click();
    await page.waitForFunction(() => document.getElementById('summary').textContent.includes('2 corrected'));

    // One acceptance and one rejection, so the export has every kind of row.
    await openComponent(page, 'FEV1 summary by visit', 'Spriometry (FEV1)', 'title');
    await page.keyboard.press('a');
    await page.waitForFunction(() => document.getElementById('summary').textContent.startsWith('1 accepted'));
    await page.keyboard.press('j');
    await page.keyboard.press('x');
    await page.waitForFunction(() => document.getElementById('summary').textContent.includes('1 rejected'));
    console.log('summary:', await page.locator('#summary').textContent());
  } else {
    console.log('summary after restart:', await page.locator('#summary').textContent());
    await openComponent(page, 'Subject-level spirometry', 'Full Analysis Set', 'population label');
    console.log('reviewer-added passage shown after restart:', await page.locator('#source-pane h2', { hasText: 'Passages added by the reviewer' }).count() === 1);
    console.log('its quotation is highlighted:', await page.locator('#source-pane .card', { hasText: 'Added 1' }).locator('mark').count() >= 1);
    await openComponent(page, 'FEV1 summary by visit', 'Full Analysis Set', 'population label');
    console.log('correction shown:', (await page.locator('#detail-pane').textContent()).includes('Section 5.3 defines the Full Analysis Set'));
    console.log('highlighted quotations in candidates:', await page.locator('#source-pane mark').count());
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: 'Export matrix (CSV)' }).click()]);
    await download.saveAs(out + '/traceability-matrix.csv');
    console.log('exported:', download.suggestedFilename(), fs.statSync(out + '/traceability-matrix.csv').size, 'bytes');
    await page.screenshot({ path: out + '/after-restart.png' });
  }
  console.log('page errors:', JSON.stringify(errors));
  await browser.close();
})().catch(error => { console.error('FAILED:', error.message); process.exit(1); });
