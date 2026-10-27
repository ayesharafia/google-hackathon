import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {createRequire} from 'node:module';
const f=JSON.parse(await readFile('.backend/groq-runtime.json','utf8'));
if(process.env.PHYSIMESH_BROWSER_DISPOSABLE!=='1'||new URL(f.base).hostname!=='127.0.0.1')throw Error('Disposable loopback required');
const {chromium}=createRequire(import.meta.url)(process.env.PHYSIMESH_PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(f.base+'/web/workbench.html');await page.locator('#token').fill(f.token);await page.locator('#connection button').click();await page.waitForFunction(()=>!document.querySelector('#projects').disabled);await page.locator('#projects').selectOption(f.project_id);await page.locator('#open').click();await page.waitForFunction(pid=>document.querySelector('#project-record').textContent.includes(pid),f.project_id);
 await page.locator('#groq-key').fill('synthetic-groq-key');await page.locator('#groq-prompt').fill('Inspect the design');await page.getByRole('button',{name:'Send message'}).click();await page.getByText('The saved design is available.').waitFor();assert.match(await page.locator('.groq-transcript').innerText(),/design.get.*completed/);
 assert.equal(await page.evaluate(()=>JSON.stringify([localStorage,sessionStorage]).includes('synthetic-groq-key')),false);
 await page.locator('#groq-prompt').fill('Change duration to 8 minutes');await page.getByRole('button',{name:'Send message'}).click();await page.getByRole('button',{name:'Approve and run',exact:true}).waitFor();
 await mkdir('docs/qa/assets/groq-chat',{recursive:true});await page.locator('.groq-review').screenshot({path:'docs/qa/assets/groq-chat/review.png'});assert.match(await page.locator('.groq-review').innerText(),/mission.duration_s/);assert.match(await page.locator('#save-state').innerText(),/version 1/);
 await page.getByRole('button',{name:'Approve and run',exact:true}).click();await page.getByRole('button',{name:'Continue with Groq'}).waitFor();assert.match(await page.locator('#save-state').innerText(),/version 2/);
 await page.getByRole('button',{name:'Continue with Groq'}).click();await page.getByText('The reviewed change was saved.').waitFor();
 await page.locator('#groq-prompt').fill('Change duration again');await page.getByRole('button',{name:'Send message'}).click();await page.getByRole('button',{name:'Reject',exact:true}).click();await page.getByRole('button',{name:'Continue with Groq'}).waitFor();assert.match(await page.locator('#save-state').innerText(),/version 2/);await page.getByRole('button',{name:'Continue with Groq'}).click();await page.getByText('The change was rejected.').waitFor();

 await mkdir('docs/qa/assets/groq-chat',{recursive:true});await page.locator('#groq-key').fill('');
 for(const [name,width,zoom] of [['desktop',1440,1],['phone',390,1],['enlarged',1440,2]]){await page.setViewportSize({width,height:1000});await page.evaluate(z=>document.body.style.zoom=z,zoom);await page.locator('#groq-chat').screenshot({path:`docs/qa/assets/groq-chat/${name}.png`});}
 await page.evaluate(()=>document.body.style.zoom='1');await page.locator('#groq-key').fill('synthetic-groq-key');await page.getByRole('button',{name:'Clear conversation and key'}).click();assert.equal(await page.locator('#groq-key').inputValue(),'');assert.equal(await page.locator('.groq-message').count(),0);assert.deepEqual(errors,[]);
 console.log('Browser passed: fake-provider read, rendered action, key storage/clear, responsive captures, no page errors.');
}finally{await browser.close();}
