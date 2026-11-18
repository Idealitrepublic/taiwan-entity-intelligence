/** Real Development/Preview UI → report API → downloaded PDF. No route fixtures. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require('playwright');
(async()=>{
 const base=process.env.TEI_AUDIT_BASE_URL||'http://127.0.0.1:3107/';
 const parsed=new URL(base);
 assert(['127.0.0.1','localhost'].includes(parsed.hostname)||/^taiwan-entity-intelligence-.+\.vercel\.app$/.test(parsed.hostname),'Only local or Preview acceptance is allowed');
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEI_BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({acceptDownloads:true,viewport:{width:1440,height:900}}),errors=[],responses=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.url().includes('/api/v1/reports/'))responses.push(r.status())});
  // A deployment-specific, expiring authenticated entry URL may be supplied in
  // a private local file. Never write it into reports, screenshots or console.
  const entry=process.env.TEI_AUDIT_ENTRY_FILE?fs.readFileSync(process.env.TEI_AUDIT_ENTRY_FILE,'utf8').trim():base;
  assert.equal(new URL(entry).origin,parsed.origin);
  await page.goto(entry);
  await page.locator('#q').fill('22659295');await page.locator('#search').click();
  await page.locator('.company-overview-name').waitFor({timeout:45000});
  const download=page.waitForEvent('download',{timeout:120000});
  await page.getByRole('button',{name:'下載完整調查 PDF / Download PDF',exact:true}).click();
  const file=await download;
  const path=process.env.TEI_AUDIT_PDF_PATH||'/tmp/tei-real-company-download.pdf';
  await file.saveAs(path);
  assert.equal(await file.failure(),null);
  const bytes=fs.readFileSync(path);
  assert.equal(bytes.subarray(0,5).toString(),'%PDF-');assert(bytes.length>10000);
  assert(file.suggestedFilename().endsWith('.pdf'));assert.deepEqual(responses,[200]);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',filename:file.suggestedFilename(),bytes:bytes.length,report_http:responses,console_errors:errors.length}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.message.replace(/https?:\/\/\S+/g,'[URL suppressed]'));process.exitCode=1});
