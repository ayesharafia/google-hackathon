import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)(process.env.PHYSIMESH_PLAYWRIGHT_MODULE||'playwright');
if(process.env.PHYSIMESH_BROWSER_DISPOSABLE!=='1')throw new Error('Disposable flag required.');
const browser=await chromium.launch({channel:'chrome',headless:true}),checks=[],errors=[];
try{
 for(const mode of ['hosted','public']){
  const fixture=JSON.parse(await readFile('.backend/agent-'+mode+'-runtime.json','utf8'));
  if(new URL(fixture.base).hostname!=='127.0.0.1')throw new Error('Loopback fixture required.');
  const context=await browser.newContext(),page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(fixture.base+'/web/workbench.html');
  if(mode==='hosted'){
   await page.locator('#individual-login:not([hidden])').waitFor();await page.locator('#login-email').fill('viewer@example.test');await page.locator('#login-password').fill(fixture.password);await page.locator('#individual-login button').click();
  }
  await page.waitForFunction(()=>!document.querySelector('#projects').disabled);
  await page.locator('#projects').selectOption(fixture.project_id);await page.locator('#open').click();
  await page.waitForFunction(pid=>document.querySelector('#project-record').textContent.includes(pid),fixture.project_id);
  if(mode==='hosted'){
   assert.equal(await page.locator('#agent-reviewed').isDisabled(),true);checks.push('Actual hosted viewer cannot enable change/study grant groups');
   await page.locator('#agent-client-name').fill('Viewer read client');await page.getByRole('button',{name:'Create AI connection',exact:true}).click();await page.locator('.agent-credential:not([hidden])').waitFor();const credential=await page.locator('#agent-credential').inputValue();
   const headers={Authorization:'Bearer '+credential};const response=await context.request.post(fixture.base+'/api/drone/agent/actions/design.inspect',{headers,data:{request_id:crypto.randomUUID().replaceAll('-',''),arguments:{project_id:fixture.project_id}}});assert.equal(response.status(),200);checks.push('Viewer-created credential performs a real saved-input read');
   const denied=await context.request.post(fixture.base+'/api/drone/agent/actions/design.propose',{headers,data:{request_id:crypto.randomUUID().replaceAll('-',''),arguments:{project_id:fixture.project_id,expected_version:1,edits:[]}}});assert.equal(denied.status(),403);
   await page.locator('#agent-workspace summary').filter({hasText:'Prepare a project change'}).click();assert.equal(await page.getByRole('button',{name:'Preview change',exact:true}).isDisabled(),true);checks.push('Actual viewer proposal controls and API writes are both denied');
   await page.getByRole('button',{name:'Clear credential from this page',exact:true}).click();await page.locator('#logout').click();assert.equal(await page.locator('#agent-client-name').isDisabled(),true);assert.equal(await page.locator('#agent-credential').inputValue(),'');checks.push('Hosted logout clears credentials and disables AI controls');
  }else{
   assert.equal(await page.locator('#agent-client-name').isDisabled(),true);assert.equal(await page.locator('#agent-refresh').isDisabled(),true);assert.match(await page.locator('#agent-status').innerText(),/authenticated workspace/);checks.push('Public demo visibly explains why privileged AI connections are disabled');
   const denied=await context.request.get(fixture.base+'/api/drone/agent/catalog');assert.equal(denied.status(),403);assert.equal(await page.locator('#project-title').isEnabled(),true);checks.push('Public gateway is denied while existing manual project authoring remains available');
  }
  await context.close();
 }
 assert.deepEqual(errors,[]);checks.push('Hosted-viewer and public pages have no JavaScript errors');
}finally{await writeFile('docs/qa/assets/ai-foundation/modes-results.json',JSON.stringify({checks,errors},null,2));await browser.close();}
console.log(JSON.stringify({passed:checks.length},null,2));
