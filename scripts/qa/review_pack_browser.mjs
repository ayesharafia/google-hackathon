/* Synthetic disposable archive download acceptance; never targets client data. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import path from 'node:path';
const base=process.env.PHYSIMESH_BROWSER_BASE_URL;
if(!base||!['localhost','127.0.0.1'].includes(new URL(base).hostname)||process.env.PHYSIMESH_BROWSER_DISPOSABLE!=='1')throw new Error('Explicit disposable loopback server required.');
const {chromium}=createRequire(import.meta.url)(process.env.PHYSIMESH_PLAYWRIGHT_MODULE||'playwright');
const evidence=path.resolve(process.env.PHYSIMESH_BROWSER_EVIDENCE_DIR||'.backend/review-pack-evidence');await mkdir(evidence,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});const context=await browser.newContext({viewport:{width:1440,height:1100},reducedMotion:'reduce'});const page=await context.newPage(),checks=[],errors=[];let downloads=0;page.on('pageerror',e=>errors.push(e.message));page.on('download',()=>downloads++);page.on('dialog',d=>d.accept());page.setDefaultTimeout(10000);
const root=page.locator('#review-pack'),status=page.locator('#review-pack-status'),button=page.locator('#export-pack'),mark=t=>{checks.push(t);console.log('PASS '+t);};
const idle=()=>page.waitForFunction(()=>!document.querySelector('#snapshot').disabled,{},{timeout:20000});
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
async function download(){const pending=page.waitForEvent('download');await button.click();const result=await pending;await idle();return {bytes:await readFile(await result.path()),path:await result.path(),name:result.suggestedFilename()};}
const inspect=filename=>JSON.parse(execFileSync('python3',['-c',`import json,zipfile,hashlib,sys
with zipfile.ZipFile(sys.argv[1]) as archive:
 names=archive.namelist();assert names==sorted(set(names));assert len(names)<=128
 assert sum(i.file_size for i in archive.infolist())<=40*1024*1024
 assert all(not n.startswith('/') and '..' not in n.split('/') for n in names)
 data={n:archive.read(n) for n in names};hashes=json.loads(data['hashes.json'])
 assert set(hashes)==set(data)-{'hashes.json'}
 for n,v in hashes.items():assert v=={'sha256':hashlib.sha256(data[n]).hexdigest(),'bytes':len(data[n])}
 for n,raw in data.items():
  if n.startswith('sources/'):assert hashlib.sha256(raw).hexdigest()==n.split('/')[1][:-5]
 assert data['report.pdf'].startswith(b'%PDF-')
 m=json.loads(data['manifest.json']);r=json.loads(data['study.json'])
 assert m['snapshot_json_sha256']==hashlib.sha256(data['snapshot.json']).hexdigest()
 assert m['snapshot_hash_scheme']=='si_numeric_snapshot_v1'
 assert r['study_sha256']==m['study_sha256'];assert hashlib.sha256(data['report.pdf']).hexdigest()==m['pdf_sha256']
 print(json.dumps({'manifest':m,'snapshot':json.loads(data['snapshot.json']),'result_sha':hashlib.sha256(data['study.json']).hexdigest(),'members':names}))`,filename],{encoding:'utf8'}));
async function evaluate(){await page.locator('#freeze').click();await idle();await page.locator('#calculate').click();await idle();return page.locator('#studies button[aria-current=true]').getAttribute('data-study');}
async function fits(){assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.equal(await root.evaluate(el=>{const box=el.getBoundingClientRect();return [...el.querySelectorAll('p,h3,button,summary,li')].filter(n=>n.checkVisibility()).every(n=>{const r=n.getBoundingClientRect();return r.left>=box.left-1&&r.right<=box.right+1;});}),true);}
try{
 await page.goto(base+'/web/workbench.html');await page.locator('#example').waitFor();assert.equal(await button.isDisabled(),true);assert.match(await status.innerText(),/Select a retained study/);mark('No selected study keeps the download disabled with an explicit prompt');
 await page.locator('#example').click();await idle();const original=JSON.parse(await page.locator('#snapshot').inputValue()),pid=await page.locator('#projects').inputValue(),digest=await evaluate();const study=(await(await page.request.get(base+'/api/drone/projects/'+pid+'/studies/'+digest+'/export')).body());const record=JSON.parse(study);
 await root.getByText('Package contents and limits',{exact:true}).click();assert.match(await root.innerText(),/Excludes CAD, original CSV\/Excel/);assert.match(await root.innerText(),/40 MiB/);mark('Actual contents disclosure explains included artifacts, hard bounds and exclusions');
 const first=await download(),packet=inspect(first.path);assert.match(first.name,new RegExp(digest));assert.equal(packet.manifest.study_sha256,digest);assert.equal(packet.manifest.revision_sha256,record.specification.revision_sha256);assert.equal(packet.result_sha,sha(study));assert.deepEqual(packet.snapshot,original);assert.match(await status.innerText(),/checksum verified/i);mark('Actual ZIP download unpacks safely with exact frozen snapshot/result, valid PDF and every member checksum');
 assert.equal(packet.members.filter(n=>n.startsWith('sources/')).length,record.specification.performance_source_sha256.length);assert.ok(packet.manifest.exclusions.some(s=>s.includes('Original CSV/XLSX')));mark('Actual source members match retained references; manifest states raw-spreadsheet exclusions');
 await page.locator('#design-json>summary').click();const edited=structuredClone(original);edited.masses.items[0].mass_kg+=1;await page.locator('#snapshot').fill(JSON.stringify(edited));await page.locator('#snapshot').press('Tab');const second=await download();assert.deepEqual(second.bytes,first.bytes);assert.match(await page.locator('#review-pack-binding').innerText(),/Unsaved draft edits are excluded/);mark('Unsaved draft edits do not change exact bytes of the selected retained package');
 // UI-only queued-report fixture; actual queue permissions/publication are checked in Python.
 let queued=true;const job={job_id:'job_review_pack_fixture',kind:'report',project_id:pid,spec_json:JSON.stringify({study_sha256:digest}),state:'queued'};
 await page.route('**/review-pack',route=>{if(queued){queued=false;return route.fulfill({status:202,json:job});}return route.continue();});
 await page.route('**/jobs/job_review_pack_fixture',route=>route.fulfill({json:{...job,state:'succeeded',attempts:[],result_json:'{}'}}));
 const prepared=await download();assert.deepEqual(prepared.bytes,first.bytes);await page.unroute('**/review-pack');await page.unroute('**/jobs/job_review_pack_fixture');mark('Queued-report UI fixture waits for preparation before downloading and verifying the actual ZIP');
 let count=downloads;await page.route('**/review-pack',async route=>{const response=await route.fetch();await route.fulfill({response,headers:{...response.headers(),'x-study-sha256':'wrong'}});});await button.click();await idle();assert.equal(downloads,count);assert.match(await status.innerText(),/identity or format differs/);await page.unroute('**/review-pack');mark('Mismatched response identity refuses the download and replaces previous success status');
 await page.route('**/review-pack',async route=>{const response=await route.fetch();await route.fulfill({response,headers:{...response.headers(),'x-pack-sha256':'f'.repeat(64)}});});await button.click();await idle();assert.equal(downloads,count);assert.match(await status.innerText(),/checksum differs/);await page.unroute('**/review-pack');mark('Whole-file checksum mismatch prevents a browser download');
 await page.route('**/review-pack',route=>route.fulfill({status:422,json:{detail:'Synthetic missing retained source'}}));await button.click();await idle();assert.equal(downloads,count);assert.match(await status.innerText(),/Synthetic missing retained source/);await page.unroute('**/review-pack');mark('API refusal stays unavailable with no stale or partial ZIP download');
 const stable=await download();assert.deepEqual(stable.bytes,first.bytes);await fits();await root.getByRole('heading').click();await root.screenshot({path:path.join(evidence,'desktop.png')});await page.screenshot({path:path.join(evidence,'desktop-context.png')});
 for(const [width,zoom,name] of [[390,1,'phone'],[1440,2,'enlarged']]){await page.setViewportSize({width,height:1100});await page.evaluate(z=>document.body.style.zoom=z,zoom);await fits();await root.getByRole('heading').scrollIntoViewIfNeeded();await root.screenshot({path:path.join(evidence,name+'.png')});await page.screenshot({path:path.join(evidence,name+'-context.png')});mark(name+' layout keeps binding, text, disclosure and button inside deliberate gutters');}
 await page.evaluate(()=>document.body.style.zoom=1);await page.setViewportSize({width:1440,height:1100});await root.getByText('Package contents and limits',{exact:true}).focus();await page.keyboard.press('Enter');assert.equal(await root.locator('details').evaluate(el=>el.open),false);await page.keyboard.press('Enter');assert.equal(await root.locator('details').evaluate(el=>el.open),true);mark('Native package disclosure responds to keyboard Enter');
 let release,arrived,done;const held=new Promise(r=>release=r),seen=new Promise(r=>arrived=r),fulfilled=new Promise(r=>done=r);await page.route('**/review-pack',async route=>{const response=await route.fetch();arrived();await held;await route.fulfill({response});done();});await button.click();await seen;assert.equal(await button.isDisabled(),true);assert.equal(await button.getAttribute('aria-busy'),'true');
 // A hidden organization event is injected to exercise context invalidation while
 // normal workspace controls are disabled; this is not an ordinary user journey.
 await page.locator('#organization').evaluate(el=>el.dispatchEvent(new Event('change',{bubbles:true})));release();await fulfilled;await page.waitForFunction(()=>!document.querySelector('#example').disabled,{},{timeout:10000});assert.equal(downloads,count+1);assert.match(await status.innerText(),/Select a retained study/);assert.equal(await button.isDisabled(),true);await page.unroute('**/review-pack');mark('Pending controls disable; injected workspace invalidation suppresses a delayed ZIP');
 await page.locator('#realistic-example').click();await idle();const conditioned=await evaluate(),third=await download(),closure=inspect(third.path);assert.equal(closure.manifest.study_sha256,conditioned);assert.ok(closure.manifest.source_dependencies.some(s=>s.raw_source_sha256));for(const link of closure.manifest.source_dependencies)if(link.raw_source_sha256)assert.ok(closure.members.includes('sources/'+link.raw_source_sha256+'.json'));mark('Actual conditioned-map study download contains its referenced raw JSON dependencies');
 assert.deepEqual(errors,[]);mark('No browser JavaScript errors');
}finally{await writeFile(path.join(evidence,'results.json'),JSON.stringify({checks,errors},null,2));await browser.close();}
console.log(JSON.stringify({passed:checks.length,checks,evidence},null,2));
