/** Exercise source text and official lookup tabs in a real browser. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');

const html = fs.readFileSync(process.env.TEI_TEST_HTML || 'web/index.html', 'utf8');
const a = {id:'003e0ccc-1f16-55cc-89d3-570d74a48ea8',entity_type:'Company',display_name:'聯上開發股份有限公司',public_identifier:'22659295'};
const b = {id:'446eca14-e58c-5984-b308-d7e9057523b2',entity_type:'Company',display_name:'敦峰汽車工業股份有限公司',public_identifier:'54690903'};
const middle = {id:'f58f140f-d9df-53ff-9344-45eb49a40064',entity_type:'Politician',display_name:'吳思瑤'};
const agency = {id:'00000000-0000-4000-8000-000000000002',entity_type:'GovernmentAgency',display_name:'來源機關與跨機關聯絡處 / Public Evidence Agency'};
const proof = index => ({
  id:'evidence-'+index,source_name:'監察院政治獻金公開查閱平臺 / Official Political Contribution Source',
  source_record_id:'168061:taipei:incomes:3273:'+'LongSourceIdentifier'.repeat(7),
  source_url:'https://example.gov.tw/search?record='+'long-public-record-'.repeat(14),
  retrieved_at:'2026-10-28T15:55:34.995029+00:00',
  title:'政治獻金來源紀錄：敦峰汽車工業股份有限公司 / Evidence with a long bilingual source title'
});
function segment(from,to,index,reverse=false) {
  return {from_entity:from,to_entity:to,traversal_direction:reverse?'reverse':'forward',
    relationship:{id:'link-'+index,source_entity_id:reverse?to.id:from.id,target_entity_id:reverse?from.id:to.id,
      relationship_type:'POLITICAL_CONTRIBUTION_TO',primary_evidence_id:'evidence-'+index,
      amount:200000,currency:'TWD',start_date:'2023-10-17'},
    evidence:proof(index)};
}
const registry = node => ({status:'ok',public_graph_scope:true,uniform_number:node.public_identifier,
  company_name:node.display_name,company:{Business_Accounting_NO:node.public_identifier,
    Company_Name:node.display_name,Responsible_Name:'負責人',Company_Location:'臺北市信義區'+'長地址'.repeat(30)},
  people:[],graph:{nodes:[{id:'company:'+node.public_identifier,type:'company',label:node.display_name}],edges:[]},
  evidence:[],evidence_status:{}});
const awards = node => ({status:'ok',matched:node.id===a.id?7:5,source:'公開決標公告 / Award source',
  records:Array.from({length:node.id===a.id?7:5},(_,index)=>({
    id:node.id+'-award-'+index,title:node.display_name+'真實流程測試公告 案件'+index,
    unit_id:'3.13.31',job_number:'0630800011',notice_filename:'BDM-1-53131415',date:'2025-01-0'+(index+1),agency:'新北市政府',notice_type:'決標公告',
    uniform_number:node.public_identifier,award_role:'winner',
    awardee_names:[node.display_name],source_url:'https://example.gov.tw/award/'+index
  }))});

(async()=>{
  const browser = await chromium.launch({headless:true,executablePath:process.env.TEI_BROWSER_PATH ||
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.setDefaultTimeout(10000);
    const errors=[];
    const privateRequests=[];
    page.on('request',request=>{
      if(/\/api\/v1\/(?:workspace|watchlist|alerts)|\/auth\/v1\//.test(request.url()))privateRequests.push(new URL(request.url()).pathname);
    });
    await page.addInitScript(()=>sessionStorage.setItem('tei_workspace_session',JSON.stringify({access_token:'test-only-stale-session',refresh_token:'test-only'})));
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('https://tei.local/**',async route=>{
      const url=new URL(route.request().url()),path=url.pathname;
      if(path==='/'||path.startsWith('/entity/'))return route.fulfill({status:200,contentType:'text/html',body:html});
      let data={};
      if(path==='/api/v1/paths')data={data:{found:true,depth:2,max_depth:2,source_entity:a,target_entity:b,
        segments:[segment(a,middle,1),segment(middle,b,2,true)]}};
      if(path.startsWith('/api/v1/graph/')) {
        const id=path.split('/').pop(),node=[a,b,middle,agency].find(n=>n.id===id);
        data={data:{nodes:[node],edges:[],has_more:false}};
      }
      if(path.startsWith('/api/v1/entities/')) {
        const node=[a,b,middle,agency].find(n=>n.id===path.split('/').pop()) || a;
        data={data:{...node,identity_status:'EXACT',evidence:[{fact_type:'source',evidence:proof(3)}]}};
      }
      if(path.startsWith('/api/company/'))data=registry(path.endsWith(b.public_identifier)?b:a);
      if(path.startsWith('/api/company-related/'))data={status:'ok',items:[]};
      if(path.startsWith('/api/procurement/')) {
        await new Promise(resolve=>setTimeout(resolve,60));
        data=awards(path.endsWith(b.public_identifier)?b:a);
      }
      if(path==='/api/procurement-detail')data={status:'ok',source_name:'OpenFun',retrieved_at:'2026-11-18',summary:[
        {label:'預算金額 / Budget',value:'0元 原因：收入性質',source_field:'已公告資料:預算金額'},
        {label:'總決標金額 / Total award amount',value:'228,900,001元',source_field:'決標資料:總決標金額'},
        {label:'決標日期 / Award date',value:'109/06/03',source_field:'決標資料:決標日期'}],bidders:[[
          {label:'廠商 / Bidder',value:'範例廠商',source_field:'投標廠商:投標廠商1:廠商名稱'},
          {label:'廠商代碼 / Bidder ID',value:'01234567',source_field:'投標廠商:投標廠商1:廠商代碼'}]],items:[]};
      if(path==='/api/v1/workspace-config')data={auth_enabled:false};
      if(path==='/api/status')data={supabase:{connected:true,partial:true,canonical:{companies:472}},source_notices:[]};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
    });
    await page.goto('https://tei.local/');
    assert.equal(await page.locator('#workspaceOpen,#watchlistOpen,#workspaceDialog,form[type="password"],input[type="password"]').count(),0);
    assert.equal(await page.locator('#systemStatus').isVisible(),false);
    assert.equal(await page.locator('#sample').textContent(),'載入真實範例 / Load real example');
    assert.deepEqual(await page.locator('#entityTypeFilter option').evaluateAll(els=>els.map(el=>el.value)),
      ['', 'Company','Politician','GovernmentOfficial','GovernmentAgency','PoliticalParty','CivilOrganization','Contract']);
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('tei_workspace_session')),null);
    await page.locator('#q').fill('x');
    await page.locator('#search').click();
    assert.match(await page.locator('#uniform').textContent(),/Enter at least 2 characters/);
    async function targetHeader(width) {
      const result=await page.locator('.target-entity').evaluate(el=>{
        const box=el.getBoundingClientRect();
        return {fits:el.scrollWidth<=el.clientWidth+1,clipped:[...el.querySelectorAll('#company,#uniform,.kv span')].filter(child=>{
          const r=child.getBoundingClientRect();return r.left<box.left-1||r.right>box.right+1||child.scrollWidth>child.clientWidth+1;
        }).map(child=>child.textContent)};
      });
      assert.deepEqual(result,{fits:true,clipped:[]},width+'px target text needs no horizontal scrolling');
    }
    async function searchButtons(width) {
      const buttons=await page.locator('#search,#sample').evaluateAll(els=>els.map(el=>{
        const range=document.createRange();range.selectNodeContents(el);
        const lines=new Set([...range.getClientRects()].map(r=>Math.round(r.top)));
        const box=el.getBoundingClientRect();
        return {singleLine:lines.size===1,fits:el.scrollWidth<=el.clientWidth+1,
          onScreen:box.left>=0&&box.right<=innerWidth+1};
      }));
      assert.deepEqual(buttons,[{singleLine:true,fits:true,onScreen:true},{singleLine:true,fits:true,onScreen:true}],
        width+'px search and real-example buttons show all text on one line');
    }
    for(const width of [1920,1600,1440,1280,1121,1024,768,390,320]) {
      await page.setViewportSize({width,height:900});
      await searchButtons(width);
      await targetHeader(width);
    }
    await page.setViewportSize({width:1440,height:900});
    await page.locator('#sample').click();
    await page.locator('#pathResult .path-segment').nth(1).waitFor();

    async function toolbar(label) {
      await page.waitForFunction(()=>{
        const bar=document.querySelector('.graphbar').getBoundingClientRect();
        return document.querySelector('#svg').getBoundingClientRect().top>=bar.bottom;
      });
      const result=await page.evaluate(()=>{
        const tools=document.querySelector('.graphbar .tools').getBoundingClientRect();
        const actions=document.querySelector('.graph-actions').getBoundingClientRect();
        const bar=document.querySelector('.graphbar').getBoundingClientRect();
        const outside=[...document.querySelectorAll('.graphbar button')].filter(el=>{
          if(!el.getClientRects().length)return false;
          const box=el.getBoundingClientRect();
          return box.left<bar.left-1||box.right>bar.right+1;
        }).map(el=>el.textContent);
        return {below:actions.top>=tools.bottom,outside};
      });
      assert.deepEqual(result,{below:true,outside:[]},label);
    }

    for(const node of [a,b]) {
      const oldPositions=await page.locator('#svg .node').evaluateAll(els=>els.map(el=>({id:el.dataset.nodeId,
        x:el.querySelector('circle:not(.hit)').getAttribute('cx'),y:el.querySelector('circle:not(.hit)').getAttribute('cy')})));
      const scale=await page.locator('#zoomValue').textContent();
      await page.locator(`#svg .node[data-node-id="${node.id}"]`).press('Enter');
      const count=awards(node).records.length;
      await page.locator('#overviewPane .company-overview-awards .record').nth(count-1).waitFor({state:'attached'});
      assert.equal(await page.locator('#overviewPane').isVisible(),true,
        'Company selection keeps its profile visible together with its awards');
      assert.equal(await page.locator('#overviewPane .company-overview-name').textContent(),node.display_name);
      assert.match(await page.locator('#overviewPane .kv').first().textContent(),new RegExp(node.public_identifier));
      assert.equal(await page.locator('#overviewPane .company-overview-awards .record').count(),count);
      assert.equal(await page.locator('#overviewPane').evaluate(el=>{
        const summary=document.querySelector('#connectionSummary');
        return Boolean(el.compareDocumentPosition(summary)&Node.DOCUMENT_POSITION_FOLLOWING);
      }),true,'the selected company profile comes before the connection summary');
      const inViewport=await page.locator('#overviewPane .company-overview-name').evaluate(el=>{
        const p=el.closest('.panel').getBoundingClientRect(),r=el.getBoundingClientRect();
        return r.top>=p.top&&r.bottom<=Math.min(p.bottom,innerHeight);
      });
      assert(inViewport,'the actual company name must be on screen, not just attached below the summary');
      await page.waitForFunction(()=>document.querySelector('#svg').getAttribute('aria-busy')==='false');
      const positions=await page.locator('#svg .node').evaluateAll(els=>els.map(el=>({id:el.dataset.nodeId,
        x:el.querySelector('circle:not(.hit)').getAttribute('cx'),y:el.querySelector('circle:not(.hit)').getAttribute('cy')})));
      for(const old of oldPositions)assert.deepEqual(positions.find(p=>p.id===old.id),old,'expansion keeps existing nodes fixed');
      assert.equal(await page.locator('#zoomValue').textContent(),scale,'expansion preserves the current zoom');
      assert.equal(await page.locator('#pathEntitySelect').inputValue(),node.id);
      assert.equal(await page.locator('#tabProcurementCount').textContent(),count+' 筆 / records');
    }
    await page.locator('.tab[data-tab="overview"]').click();

    async function layout(label) {
      const result=await page.evaluate(()=>{
        const nodes=[...document.querySelectorAll('.panel .section-head>*,.panel .kv span,.panel .card p,.panel .card a,.panel .notice,.panel .title,.panel .sub')];
        const clipped=nodes.filter(el=>{
          if(!el.getClientRects().length)return false;
          const box=el.getBoundingClientRect(),panel=el.closest('.panel').getBoundingClientRect();
          const card=el.closest('.card')?.getBoundingClientRect();
          return box.left<panel.left-1||box.right>panel.right+1||
            (card&&(box.left<card.left-1||box.right>card.right+1));
        }).map(el=>el.textContent.slice(0,50));
        const overflow=[...document.querySelectorAll('.panel')].filter(el=>el.scrollWidth>el.clientWidth+1)
          .map(el=>el.className);
        const wrapped=[];
        const inaccessible=[...document.querySelectorAll('.left .section')].filter(el=>el.scrollWidth>el.clientWidth+1).length;
        const blocked=[...document.querySelectorAll('.left *')].filter(el=>el.getClientRects().length&&getComputedStyle(el).textOverflow==='ellipsis').map(el=>el.textContent.slice(0,30));
        return {clipped,overflow,wrapped,inaccessible,blocked,pageOverflow:document.documentElement.scrollWidth>innerWidth+1};
      });
      assert.deepEqual(result,{clipped:[],overflow:[],wrapped:[],inaccessible:0,blocked:[],pageOverflow:false},label);
    }

    async function checkAwards(node,label) {
      await page.locator('.tab[data-tab="procurement"]').click();
      const pane=page.locator('#procurementPane'),count=awards(node).records.length;
      await pane.locator('.record').nth(count-1).waitFor({state:'attached'});
      assert.equal(await pane.locator('.record').count(),count,label+' includes every loaded award');
      assert.equal(await page.locator('#connectionSummary').isVisible(),false,label+' not covered by summary');
      assert.equal(await page.locator('#tabProcurementCount').textContent(),count+' 筆 / records');
      if(await pane.locator('.notice').count())
        assert.match(await pane.locator('.notice').first().textContent(),new RegExp(node.display_name));
      await pane.locator('.record').first().locator('summary').click();
      assert.equal(await pane.locator('.record').first().locator('a').first().isVisible(),true);
      await pane.locator('.award-detail-content h4').first().waitFor();
      assert.match(await pane.locator('.award-detail-content').first().textContent(),/228,900,001元/);
      assert.match(await pane.locator('.award-detail-content').first().textContent(),/0元 原因/);
      const bidders=pane.locator('.award-detail-content details').first();
      assert.equal(await bidders.getAttribute('open'),null,'bidder breakdown starts collapsed');
      await bidders.locator('summary').click();
      assert.equal(await bidders.getByText('01234567',{exact:true}).isVisible(),true);
      await layout(label+' key award details');
      await pane.getByRole('searchbox',{name:'標案關鍵字 / Award keyword',exact:true}).fill('公告 案件０');
      await pane.locator('.award-keyword-search button').click();
      assert.equal(await pane.locator('.record').count(),1,'multiple words and full-width digits match loaded awards');
      await pane.getByRole('searchbox',{name:'標案關鍵字 / Award keyword',exact:true}).fill('沒有這個標案');
      await pane.locator('.award-keyword-search button').click();
      assert.equal(await pane.locator('.record').count(),0);
      assert.match(await pane.textContent(),/No award notice matches/);
      await pane.locator('.clear-filters').click();
      assert.equal(await pane.locator('.record').count(),count,'reset restores all loaded awards');
      await pane.getByRole('searchbox',{name:'標案關鍵字 / Award keyword',exact:true}).fill('新北市政府');
      await pane.locator('.award-keyword-search button').click();
      assert.equal(await pane.locator('.record').count(),count,'agency search is supported');
      await pane.locator('.clear-filters').click();
      await layout(label+' awards');
      await page.locator('.tab[data-tab="overview"]').click();
    }

    for(const width of [1440,1280,1024,768,390]) {
      await page.setViewportSize({width,height:900});
      await searchButtons(width);
      await toolbar(width+'px graph toolbar');
      if(width>1120) {
        for(let repeat=0;repeat<2;repeat++) {
          await page.locator('#graphFocus').click();
          await toolbar(width+'px focused');
          await page.locator('#graphFocus').click();
          await toolbar(width+'px panels restored');
        }
      }
      await layout(width+'px path details');
      await targetHeader(width);
      for(const [kind,url] of [['judicial','https://judgment.judicial.gov.tw/'],
        ['penalty','https://announcement.mol.gov.tw/']]) {
        await page.locator('#pathEntitySelect').selectOption(b.id);
        await page.locator('.tab[data-tab="'+kind+'"]').click();
        const pane=page.locator('#'+kind+'Pane');
        assert.equal(await pane.locator('a').count(),1);
        assert.equal(await pane.locator('a').getAttribute('href'),url);
        assert.equal(await pane.locator('.record,.notice,.filters').count(),0);
        assert.equal(await page.locator('#connectionSummary').isVisible(),false);
        assert.equal(await page.locator('#pathEntityPicker').isVisible(),false);
        await layout(width+'px '+kind+' lookup');
        await page.waitForTimeout(160);
        assert.equal(await pane.locator('a').getAttribute('href'),url,
          'Async entity details must keep the official lookup');
        await page.locator('.tab[data-tab="overview"]').click();
      }
      assert.equal(await page.locator('#connectionSummary').isVisible(),true);
      await layout(width+'px company sidebar');
      await checkAwards(b,width+'px path company B');
      await page.locator('#pathEntitySelect').selectOption(a.id);
      await checkAwards(a,width+'px path company A');
    }
    await page.locator('#pathEntitySelect').selectOption(middle.id);
    await page.locator('.tab[data-tab="procurement"]').click();
    assert.equal(await page.locator('#tabProcurementCount').textContent(),'0 筆已載入 / loaded',
      'Non-company selection must not retain the previous company award count');
    assert.equal(await page.locator('#procurementPane .record').count(),0);
    await page.locator('.tab[data-tab="overview"]').click();
    await page.setViewportSize({width:1440,height:900});
    await page.locator('#q').fill(a.public_identifier);
    await page.locator('#search').click();
    await page.locator('.company-overview-name').waitFor();
    await layout('Company search with long official address');
    await checkAwards(a,'Company investigation');
    for(const node of [a,b]) {
      await page.goto('https://tei.local/entity/'+node.id);
      await page.locator('#graphTitle').filter({hasText:node.display_name}).waitFor();
      await checkAwards(node,'Indexed company '+node.display_name);
    }
    await page.goto('https://tei.local/entity/'+agency.id);
    await page.locator('#overviewPane .detail h3').waitFor();
    for(const [kind,url] of [['judicial','https://judgment.judicial.gov.tw/'],
      ['penalty','https://announcement.mol.gov.tw/']]) {
      await page.locator('.tab[data-tab="'+kind+'"]').click();
      assert.equal(await page.locator('#'+kind+'Pane a').getAttribute('href'),url);
      assert.equal(await page.locator('#'+kind+'Pane').locator('.notice,.record,.filters').count(),0);
    }
    await page.locator('.tab[data-tab="overview"]').click();
    await layout('Agency profile and evidence');
    await page.setViewportSize({width:390,height:900});
    assert.equal(await page.locator('dialog,input[type="password"]').count(),0);
    assert.equal(await page.locator('#systemStatus').isVisible(),false);
    assert.deepEqual(privateRequests,[],'a stale session never triggers private workspace, login or alert calls');
    assert.deepEqual(errors,[]);
    console.log('Panel layout: company overview plus awards, stable node coordinates and zoom after expansion, toolbar order, official links and 1440/1280/1024/768/390px passed.');
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
