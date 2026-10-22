/* Synthetic browser acceptance. Only use an explicitly disposable loopback API. */
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';

const base = process.env.PHYSIMESH_BROWSER_BASE_URL;
if (!base || !['127.0.0.1', 'localhost'].includes(new URL(base).hostname)
    || process.env.PHYSIMESH_BROWSER_DISPOSABLE !== '1') {
  throw new Error('Set PHYSIMESH_BROWSER_BASE_URL to a disposable loopback server and PHYSIMESH_BROWSER_DISPOSABLE=1. Synthetic projects will be created.');
}
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PHYSIMESH_PLAYWRIGHT_MODULE || 'playwright');
const evidence = path.resolve(process.env.PHYSIMESH_BROWSER_EVIDENCE_DIR || '.backend/readiness-browser-evidence');
await mkdir(evidence, {recursive: true});
const browser = await chromium.launch({channel: 'chrome', headless: true});
const context = await browser.newContext({viewport: {width: 1440, height: 1100}, reducedMotion: 'reduce'});
const page = await context.newPage();
const errors = [], checks = [];
page.on('pageerror', error => errors.push(error.message));
const check = name => checks.push(name);
const inspect = async () => {
  await page.locator('#inspect-saved').click();
  await page.waitForFunction(() => document.querySelector('#readiness-status').textContent.startsWith('Inspected saved draft'));
};
const idle = () => page.waitForFunction(() => !document.querySelector('#snapshot').disabled);
const save = async () => { await page.locator('#save').click(); await idle(); await page.locator('#inspect-saved').waitFor({state: 'visible'}); };
const panel = page.locator('#engineering-readiness');
const contentFits = () => panel.evaluate(el => {
  const box = el.getBoundingClientRect();
  const elementsFit = [...el.querySelectorAll('p,h3,h4,button,li')].every(item => {
    const rect = item.getBoundingClientRect();
    if (!rect.width && !rect.height) return true;
    return rect.left >= box.left - 1 && rect.right <= box.right + 1;
  });
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let text;
  while ((text = walker.nextNode())) {
    if (!text.textContent.trim()) continue;
    const range = document.createRange(); range.selectNodeContents(text);
    if ([...range.getClientRects()].some(rect => rect.width && (rect.left < box.left - 1 || rect.right > box.right + 1))) return false;
  }
  return elementsFit;
});

try {
  await page.goto(base + '/web/workbench.html');
  await page.locator('#project-title').fill('Synthetic readiness acceptance');
  await page.locator('#create').click(); await idle(); await inspect();
  assert.match(await panel.innerText(), /Needs attention/);
  assert.match(await panel.innerText(), /Missing or invalid inputs/);
  assert.match(await panel.innerText(), /Not eligible/);
  check('Incomplete saved project shows separate mass, pack and model gaps');

  await page.locator('#example').click(); await idle(); await inspect();
  assert.equal(await panel.locator('.readiness-check').count(), 5);
  assert.match(await panel.locator('[data-check=mass]').innerText(), /Inputs complete/);
  assert.match(await panel.locator('[data-check=battery]').innerText(), /Declarations consistent/);
  assert.match(await panel.locator('[data-check=model]').innerText(), /Required inputs eligible/);
  assert.equal(await panel.locator('.readiness-cases>li').count(), 2);
  assert.match(await panel.locator('[data-check=sources]').innerText(), /Not assessed/);
  assert.match(await panel.locator('[data-check=review]').innerText(), /Pending qualified review/);
  check('Actual synthetic saved design preserves per-case eligibility and unassessed/pending evidence states');
  const goodProject = await page.locator('#projects').inputValue();

  for (const group of ['mass', 'battery', 'cases', 'rotors']) {
    await panel.locator(`[data-readiness-target=${group}]`).first().click();
    assert.equal(await page.locator(`[data-readiness-group=${group}]`).getAttribute('open'), '');
    assert.equal(await page.evaluate(() => document.activeElement?.tagName), 'SUMMARY');
  }
  check('All four default editor actions open the correct group and move keyboard focus');
  await page.locator('#inspect-saved').focus(); await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement?.dataset.readinessTarget), 'mass');
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.activeElement?.parentElement?.dataset.readinessGroup), 'mass');
  check('Readiness actions work from keyboard');

  const massInput = page.locator('[data-readiness-group=mass]').getByLabel('Mass, kg', {exact: true}).first();
  await massInput.fill('11');
  assert.match(await page.locator('#readiness-status').innerText(), /Checks out of date/);
  assert.equal(await page.locator('#inspect-saved').isDisabled(), true);
  assert.doesNotMatch(await panel.innerText(), /Required inputs eligible|Declarations consistent/);
  await save(); await inspect();
  assert.match(await page.locator('#readiness-status').innerText(), /saved draft 2/);
  check('Structured edit clears previous results; saving permits inspection of the new version');

  await page.locator('#design-json>summary').click();
  const raw = JSON.parse(await page.locator('#snapshot').inputValue());
  raw.mission.cases[0].source_note += ' / synthetic UI edit';
  await page.locator('#snapshot').fill(JSON.stringify(raw)); await page.locator('#snapshot').press('Tab');
  assert.match(await page.locator('#readiness-status').innerText(), /Checks out of date/);
  await save(); await inspect();
  check('Raw JSON edits also invalidate readiness');

  // Hold a real inspection reply while making a legitimate editable change
  // through the existing secondary inspection entry point (not a forced event).
  let release, intercepted;
  const held = new Promise(resolve => { release = resolve; });
  const started = new Promise(resolve => { intercepted = resolve; });
  const delay = async route => { const response = await route.fetch(); intercepted(); await held; await route.fulfill({response}); };
  await page.route('**/inspection', delay);
  await page.getByRole('button', {name: 'Inspect saved mass and readiness', exact: true}).click();
  await started;
  await page.locator('[data-readiness-group=mass]>summary').click();
  if (!await massInput.isVisible()) await page.locator('[data-readiness-group=mass]>summary').click();
  await massInput.fill('12'); release();
  await page.waitForFunction(() => document.querySelector('#inspection-report').textContent.includes('Inputs changed'));
  assert.match(await page.locator('#readiness-status').innerText(), /Checks out of date/);
  assert.doesNotMatch(await panel.innerText(), /Required inputs eligible/);
  await page.unroute('**/inspection', delay);
  await save(); await inspect();
  check('Late real inspection reply cannot overwrite edits or revive previous passing checks');

  const diagnostic = async route => {
    const response = await route.fetch(), data = await response.json();
    data.hover_readiness.eligible = false;
    data.hover_readiness.blocking = ['<img src=x onerror=alert(1)>', 'unfamiliar backend diagnostic',
      'map outside coverage', 'payload domain reversed', 'sequence segment duration'];
    await route.fulfill({response, json: data});
  };
  await page.route('**/inspection', diagnostic); await inspect();
  assert.equal(await panel.locator('img').count(), 0);
  assert.match(await panel.innerText(), /<img src=x onerror=alert\(1\)>/);
  await panel.getByRole('button', {name: 'Open full input JSON', exact: true}).first().click();
  assert.equal(await page.locator('#design-json').getAttribute('open'), '');
  await panel.getByRole('button', {name: 'Open rotor sources', exact: true}).first().click();
  for (const group of ['model', 'sequence']) {
    await panel.locator(`[data-readiness-target=${group}]`).first().click();
    assert.equal(await page.locator(`[data-readiness-group=${group}]`).getAttribute('open'), '');
  }
  check('Synthetic injected diagnostic is inert text; unknown, rotor, model and sequence actions work');
  await page.unroute('**/inspection', diagnostic);

  const mismatched = async route => {
    const response = await route.fetch(), data = await response.json();
    data.draft_version += 1; await route.fulfill({response, json: data});
  };
  await page.route('**/inspection', mismatched);
  await page.locator('#inspect-saved').click();
  await page.waitForFunction(() => document.querySelector('#readiness-status').textContent.includes('changed on the server'));
  assert.doesNotMatch(await panel.innerText(), /Required inputs eligible|Declarations consistent/);
  await page.unroute('**/inspection', mismatched);
  check('Inspection version mismatch withholds results and asks for reload');

  const failure = route => route.abort('failed');
  await page.route('**/inspection', failure); await page.locator('#inspect-saved').click();
  await page.waitForFunction(() => document.querySelector('#readiness-status').textContent.includes('Inspection unavailable'));
  assert.doesNotMatch(await panel.innerText(), /Required inputs eligible|Declarations consistent/);
  await page.unroute('**/inspection', failure); await inspect();
  check('Network failure clears prior results; retry succeeds');

  let releaseSwitch, startedSwitch, finishedSwitch;
  const switchHold = new Promise(resolve => { releaseSwitch = resolve; });
  const switchStart = new Promise(resolve => { startedSwitch = resolve; });
  const switchFinished = new Promise(resolve => { finishedSwitch = resolve; });
  const delayedProject = async route => { const response = await route.fetch(); startedSwitch(); await switchHold; await route.fulfill({response}); finishedSwitch(); };
  await page.route('**/inspection', delayedProject);
  await page.getByRole('button', {name: 'Inspect saved mass and readiness', exact: true}).click();
  await switchStart;
  await page.locator('#project-title').fill('Synthetic context switch');
  await page.locator('#create').click(); await idle(); releaseSwitch();
  await switchFinished;
  await page.unroute('**/inspection', delayedProject);
  assert.match(await page.locator('#design-title').innerText(), /Synthetic context switch/);
  assert.doesNotMatch(await panel.innerText(), /Required inputs eligible|Declarations consistent/);
  await page.locator('#projects').selectOption(goodProject);
  await page.locator('#open').click(); await idle(); await inspect();
  check('Late inspection for a previous project cannot populate the new project panel');

  await page.locator('#freeze').click(); await idle();
  await page.locator('#revisions button').first().click(); await idle();
  await page.waitForFunction(() => document.querySelector('#display-context').textContent.includes('frozen revision'));
  await inspect();
  assert.match(await page.locator('#readiness-status').innerText(), /do not apply to frozen revisions/);
  assert.match(await page.locator('#display-context').innerText(), /frozen revision/);
  check('Frozen viewer context remains separate from saved-draft readiness');

  await panel.locator('.readiness-screening>summary').click();
  assert.match(await panel.locator('.readiness-screening').innerText(), /different input contract/);
  await panel.locator('.readiness-screening>summary').click();
  check('Separate supplied-point screening details expand and collapse');

  await panel.screenshot({path: path.join(evidence, 'desktop.png')});
  await page.setViewportSize({width: 390, height: 844});
  await panel.scrollIntoViewIfNeeded();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.equal(await contentFits(), true, 'Mobile panel content extends outside the panel');
  await panel.screenshot({path: path.join(evidence, 'mobile.png')});
  check('390px viewport has no document horizontal overflow and all five checks remain visible');
  await page.setViewportSize({width: 1440, height: 1100});
  await page.locator('body').evaluate(el => { el.style.zoom = '2'; });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.equal(await contentFits(), true, 'Enlarged panel content extends outside the panel');
  await panel.screenshot({path: path.join(evidence, 'zoom-200-css.png')});
  await page.locator('body').evaluate(el => { el.style.zoom = ''; });
  check('CSS 200% zoom reflows without document horizontal overflow; native browser zoom not asserted');
  await page.setViewportSize({width: 720, height: 800});
  assert.equal(await contentFits(), true, '720 CSS-pixel panel content extends outside the panel');
  await panel.screenshot({path: path.join(evidence, 'narrow-720.png')});
  await page.setViewportSize({width: 1440, height: 1100});
  check('720 CSS-pixel layout, equivalent to a halved desktop layout viewport, keeps controls and text inside the panel');

  await page.reload(); await page.waitForFunction(() => !document.querySelector('#create').disabled);
  await page.locator('#projects').selectOption(goodProject);
  await page.locator('#open').click(); await idle();
  assert.match(await page.locator('#readiness-status').innerText(), /has not been inspected here/);
  assert.doesNotMatch(await panel.innerText(), /Required inputs eligible/);
  await inspect();
  check('Reload and saved-project reopen never reuse a prior inspection');
  assert.deepEqual(errors, []);
  check('No page JavaScript errors');
  await writeFile(path.join(evidence, 'browser-checks.json'), JSON.stringify({
    kind: 'synthetic_browser_acceptance', checks, passed: checks.length, page_errors: errors,
    viewports: ['1440x1100', '390x844', '1440x1100 with CSS zoom 2', '720x800'],
    claim: 'UI behavior with disposable synthetic designs; injected diagnostics/version/failure responses are UI-only fixtures, not model results or aircraft validation.',
  }, null, 2) + '\n');
  console.log(JSON.stringify({passed: checks.length, checks, evidence}, null, 2));
} finally {
  await context.close(); await browser.close();
}
