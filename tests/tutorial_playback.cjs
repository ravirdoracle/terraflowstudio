// NODE_PATH=/path/to/node_modules node tests/tutorial_playback.cjs (requires playwright-core + Chrome)
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
(async () => {
 const executablePath=process.env.CHROME_BIN||['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/usr/bin/google-chrome','/usr/bin/chromium'].find(p=>fs.existsSync(p));
 assert(executablePath,'Set CHROME_BIN to Chrome/Chromium');
 const browser=await chromium.launch({executablePath,headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1160},acceptDownloads:true});
  const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url())});
  await page.clock.install();await page.goto(pathToFileURL(path.resolve(__dirname,'../tutorial.html')).href);
  const state=()=>page.evaluate(()=>window.tutorialState());
  const choose=key=>page.locator(`#workspace-picker button[data-workspace="${key}"]`).click();
  assert.equal((await state()).steps,10);assert.equal((await state()).playing,false);
  await page.click('#play');await page.clock.runFor(2500);assert((await state()).position>2);
  await page.click('#play');const paused=(await state()).position;await page.clock.runFor(2000);assert.equal((await state()).position,paused);
  await page.click('#next');assert.equal((await state()).index,1);
  await page.click('#play');await choose('gcp');assert.equal((await state()).playing,false);assert.equal((await state()).position,0);
  await page.locator('#transcript').evaluate(el=>{el.open=true});
  for(const [key,label,steps] of [['aws','AWS',10],['gcp','GCP',12],['azure','Azure',12],['dg','OCI DG',13],['oci','OCI DB',10]]){
   await choose(key);assert.equal((await state()).workspace,key);assert.equal((await state()).steps,steps);
   assert.equal(await page.locator('#transcript-list button').count(),steps);
   for(let i=0;i<steps;i++){
    await page.locator('#transcript-list button').nth(i).click();
    assert.equal((await state()).index,i);
    if(['gcp','azure'].includes(key)&&(await state()).view!=='terraform'){
     assert.equal(await page.locator('.actual-screen').getAttribute('data-cloud'),key);
     assert(await page.locator('.actual-screen img').evaluate(img=>img.complete&&img.naturalWidth===1500));
     const caption=await page.locator('.actual-screen figcaption').innerText();
     assert(caption.includes(key==='gcp'?'hashicorp/google':'hashicorp/azurerm'));
     if([5,6].includes(i))assert.equal(await page.locator('.actual-screen').getAttribute('data-capture'),i===5?'infrastructure':'cluster');
    }else assert.equal(await page.locator('#screen .pill.sel').innerText(),label);
    assert.equal(new URL(await page.locator('#scene-link').getAttribute('href')).pathname,'/'+key);
    assert((await page.locator('#screen').innerText()).length>50);
   }
   await page.locator('#transcript-list button').nth(key==='oci'?2:4).click();
   if(!['gcp','azure'].includes(key)){
    const form=await page.locator('.form-side').innerText();
    if(key==='oci'){assert(form.includes('DB HOME DISPLAY NAME'));assert.equal(await page.locator('.sheet').count(),0)}
    if(key==='dg')assert(form.includes('networking'));
   }
   if(key==='gcp'||key==='azure'||key==='oci')await page.screenshot({path:`/private/tmp/terraflow-tutorial-${key}.png`,fullPage:true});
  }
  await choose('dg');await page.locator('#transcript-list button').nth(5).click();
  await page.selectOption('#speed','2');await page.click('#play');await page.clock.runFor(6500);assert.equal((await state()).index,6);
  await page.click('#play');
  await page.locator('#seek').evaluate(el=>{el.value='1000';el.dispatchEvent(new Event('input',{bubbles:true}))});
  assert.equal((await state()).position,(await state()).total);assert.equal((await state()).playing,false);assert.match(await page.locator('#play').innerText(),/Replay/);
  await page.click('#play');assert.equal((await state()).index,0);assert.equal((await state()).playing,true);
  await page.clock.runFor(3600);assert.equal((await state()).index,1);await page.click('#play');
  await page.evaluate(()=>document.activeElement.blur());await page.keyboard.press('End');assert.equal((await state()).index,12);await page.keyboard.press('Home');assert.equal((await state()).index,0);
  await page.keyboard.press('Space');assert.equal((await state()).playing,true);await page.keyboard.press('Space');assert.equal((await state()).playing,false);
  // Let the whole selected walkthrough play to completion; verify automatic stopping.
  await page.selectOption('#speed','2');await page.click('#play');await page.clock.runFor((await state()).total*500+500);
  assert.equal((await state()).position,(await state()).total);assert.equal((await state()).playing,false);
  await choose('azure');await page.locator('#transcript').evaluate(el=>{el.open=false});
  const downloaded=page.waitForEvent('download');await page.click('#download');const download=await downloaded;assert.equal(download.suggestedFilename(),'Terraflow-Studio-Tutorial.html');
  const downloadedPath='/private/tmp/Terraflow-Studio-Tutorial-test.html';await download.saveAs(downloadedPath);
  assert(fs.readFileSync(downloadedPath,'utf8').includes('const baseScenes = ['));
  const offline=await browser.newPage();await offline.goto(pathToFileURL(downloadedPath).href);
  assert.equal(await offline.evaluate(()=>tutorialState().workspace),'azure');await offline.close();
  for(const key of ['aws','gcp','azure','dg','oci']){
   await choose(key);await page.setViewportSize({width:390,height:844});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),key+' mobile overflow');
  }
  await page.screenshot({path:'/private/tmp/terraflow-tutorial-mobile.png',fullPage:true});
  const direct=await browser.newPage();await direct.goto(pathToFileURL(path.resolve(__dirname,'../tutorial.html')).href+'?workspace=gcp');assert.equal(await direct.evaluate(()=>tutorialState().workspace),'gcp');await direct.close();
  assert.deepEqual(network,[]);assert.deepEqual(errors,[]);
  console.log('Passed: 57 scenes across all five workspaces, actual GCP/Azure cloud captures and resource steps/routes, playback/pause/replay, chapters, seek, 2x speed, completion, keyboard, offline download with selected workspace, direct links and responsive layout. No network calls or page errors.');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
