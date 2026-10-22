/* Explicitly disposable synthetic import/binding journey. No production target. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import path from 'node:path';

const base = process.env.PHYSIMESH_BROWSER_BASE_URL;
if (!base || !['127.0.0.1', 'localhost'].includes(new URL(base).hostname)
    || process.env.PHYSIMESH_BROWSER_DISPOSABLE !== '1') throw new Error('Explicit disposable loopback server required. Synthetic projects/sources will be created.');
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PHYSIMESH_PLAYWRIGHT_MODULE || 'playwright');
const evidence = path.resolve(process.env.PHYSIMESH_BROWSER_EVIDENCE_DIR || '.backend/source-binding-evidence');
await mkdir(evidence, {recursive: true});
const browser = await chromium.launch({channel: 'chrome', headless: true});
const context = await browser.newContext({viewport: {width: 1440, height: 1100}, reducedMotion: 'reduce'});
const page = await context.newPage(), checks = [], errors = [];
page.on('pageerror', error => errors.push(error.message));
const idle = () => page.waitForFunction(() => !document.querySelector('#snapshot').disabled);
const current = async () => JSON.parse(await page.locator('#snapshot').inputValue());
const group = page.locator('[data-readiness-group=rotors]');
const preview = page.locator('.source-binding');
const openRotors = async () => { if (await group.getAttribute('open') === null) await group.locator('summary').first().click(); };
const upload = async raw => {
  await openRotors();
  await group.getByLabel('Import performance JSON', {exact: true}).setInputFiles({name: 'synthetic-rotor-map.json', mimeType: 'application/json', buffer: Buffer.from(raw)});
  await preview.getByRole('heading', {name: 'Imported rotor source', exact: true}).waitFor();
};
const mark = text => checks.push(text);
const assertFits = async () => {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.equal(await preview.evaluate(el => {
    const box = el.getBoundingClientRect(), walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) { const range = document.createRange(); range.selectNodeContents(n); if ([...range.getClientRects()].some(r => r.width && (r.left < box.left-1 || r.right > box.right+1))) return false; }
    return true;
  }), true);
};

try {
  await page.goto(base + '/web/workbench.html');
  await page.locator('#example').click(); await idle();
  const pid = await page.locator('#projects').inputValue(), original = await current();
  await page.locator('#freeze').click(); await idle();
  const frozen = await page.locator('#revisions button').first().getAttribute('data-revision');
  await page.locator('#inspect-saved').click();
  await page.waitForFunction(() => document.querySelector('#readiness-status').textContent.startsWith('Inspected saved draft'));
  const modelResponse = await page.request.get(base + '/api/drone/projects/performance-sources/' + original.rotors[0].map_ref);
  assert.equal(modelResponse.status(), 200);
  const model = await modelResponse.json(); model.dataset_id = 'synthetic-source-binding-qa';
  const raw = '\n  ' + JSON.stringify(model, null, 2) + '\n';
  const digest = createHash('sha256').update(raw).digest('hex');
  await upload(raw);
  assert.match(await preview.innerText(), /synthetic-source-binding-qa/);
  assert.match(await preview.innerText(), new RegExp(digest));
  assert.equal(await preview.locator('input:checked').count(), 0);
  assert.deepEqual(await current(), original);
  mark('Import shows actual retained metadata/hash without selecting rotors or changing the draft');

  await preview.getByRole('button', {name: 'Apply source to selected rotors'}).click();
  assert.match(await preview.locator('[role=status]').innerText(), /Select at least one/);
  assert.deepEqual(await current(), original);
  mark('Empty selection refuses without changing references');

  const first = original.rotors[0].rotor_id;
  await preview.getByRole('checkbox', {name: first + ': matching configuration', exact: true}).check();
  await preview.getByRole('button', {name: 'Apply source to selected rotors'}).click();
  assert.match(await page.locator('#message').innerText(), /applied to 1 selected rotor/);
  const bound = await current();
  assert.equal(bound.rotors[0].map_ref, digest);
  assert.deepEqual(bound.rotors.slice(1), original.rotors.slice(1));
  assert.deepEqual(bound.mission, original.mission);
  assert.match(await page.locator('#readiness-status').innerText(), /Checks out of date/);
  assert.equal(await page.locator('#inspect-saved').isDisabled(), true);
  assert.equal(await page.evaluate(() => document.activeElement?.parentElement?.dataset.readinessGroup), 'rotors');
  mark('Explicit selection changes only that base-map reference, keeps case overrides, invalidates readiness and restores focus');
  if (process.env.PHYSIMESH_BROWSER_DATA_ROOT) {
    const retained = await readFile(path.join(process.env.PHYSIMESH_BROWSER_DATA_ROOT, 'artifacts/objects', digest.slice(0, 2), digest));
    assert.equal(retained.toString('utf8'), raw);
    mark('Original UTF-8 import whitespace/bytes retained exactly in the disposable artifact store');
  }
  await page.locator('#save').click(); await idle();
  await page.locator('#reload').click(); await idle();
  assert.equal((await current()).rotors[0].map_ref, digest);
  const frozenResponse = await page.request.get(base + '/api/drone/projects/' + pid + '/revisions/' + frozen);
  assert.equal(JSON.parse((await frozenResponse.json()).snapshot_json).rotors[0].map_ref, original.rotors[0].map_ref);
  mark('Saving/reopening persists binding while original frozen revision keeps its source');

  const mismatched = {...model, configuration_id: 'different-configuration'};
  await upload(JSON.stringify(mismatched));
  assert.equal(await preview.locator('input:not(:disabled)').count(), 0);
  assert.equal(await preview.getByRole('button', {name: 'Apply source to selected rotors'}).isDisabled(), true);
  mark('Mismatched configurations cannot be selected or applied');

  await upload(raw);
  await preview.getByRole('checkbox', {name: first + ': matching configuration', exact: true}).check();
  await group.getByLabel('Pitch, degrees', {exact: true}).first().fill('1');
  await preview.getByRole('button', {name: 'Apply source to selected rotors'}).click();
  assert.match(await preview.locator('[role=status]').innerText(), /Draft inputs changed/);
  assert.equal((await current()).rotors[0].pitch_deg, 1);
  assert.equal((await current()).rotors[0].map_ref, digest);
  mark('Editing after the import preview refuses stale binding instead of overwriting current edits');
  page.once('dialog', dialog => dialog.accept()); await page.locator('#reload').click(); await idle();

  let release, started, finished;
  const hold = new Promise(resolve => { release = resolve; });
  const start = new Promise(resolve => { started = resolve; });
  const done = new Promise(resolve => { finished = resolve; });
  const delay = async route => { const response = await route.fetch(); started(); await hold; await route.fulfill({response}); finished(); };
  await page.route('**/performance-sources', delay); await openRotors();
  await group.getByLabel('Import performance JSON', {exact: true}).setInputFiles({name: 'delayed.json', mimeType: 'application/json', buffer: Buffer.from(raw)});
  await start; await group.getByLabel('Pitch, degrees', {exact: true}).first().fill('2'); release(); await done;
  await page.waitForFunction(() => document.querySelector('[data-readiness-group=rotors]').textContent.includes('Inputs changed during import'));
  assert.equal(await preview.count(), 0);
  await page.unroute('**/performance-sources', delay);
  mark('A delayed import response cannot create a bindable preview after draft edits');
  page.once('dialog', dialog => dialog.accept()); await page.locator('#reload').click(); await idle();

  await upload(raw);
  await preview.screenshot({path: path.join(evidence, 'desktop.png')});
  await page.setViewportSize({width: 390, height: 844}); await assertFits();
  await preview.screenshot({path: path.join(evidence, 'mobile.png')});
  await page.setViewportSize({width: 1440, height: 1100}); await page.locator('body').evaluate(el => {el.style.zoom = '2';}); await assertFits();
  await preview.screenshot({path: path.join(evidence, 'zoom-200-css.png')});
  await page.locator('body').evaluate(el => {el.style.zoom = '';});
  mark('Phone width and CSS 200% enlargement keep metadata, choices and action inside the preview');
  assert.deepEqual(errors, []); mark('No page JavaScript errors');
  const result = {kind: 'synthetic_source_binding_acceptance', passed: checks.length, checks, page_errors: errors,
    raw_source_sha256: digest, limits: 'Synthetic source-reference/UI checks only; no measured data validity, source applicability or physical acceptance inferred. CSS enlargement is not native browser zoom.'};
  await writeFile(path.join(evidence, 'browser-checks.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 2));
} finally { await context.close(); await browser.close(); }
