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
    id:node.id+'-award-'+index,title:node.display_name+'真實流程測試公告 '+index,
    date:'2025-01-0'+(index+1),agency:'新北市政府',notice_type:'決標公告',
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
      if(path==='/api/v1/workspace-config')data={auth_enabled:false};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
    });
    await page.goto('https://tei.local/');
    await page.locator('#sample').click();
    await page.locator('#pathResult .path-segment').nth(1).waitFor();

    async function layout(label) {
      const result=await page.evaluate(()=>{
        const nodes=[...document.querySelectorAll('.panel .section-head>*,.panel .kv span,.panel .card p,.panel .card a,.panel .notice,.panel .title,.panel .sub')];
        const clipped=nodes.filter(el=>{
          if(!el.getClientRects().length)return false;
          if(el.closest('.left .section'))return false;
          const box=el.getBoundingClientRect(),panel=el.closest('.panel').getBoundingClientRect();
          const card=el.closest('.card')?.getBoundingClientRect();
          return box.left<panel.left-1||box.right>panel.right+1||
            (card&&(box.left<card.left-1||box.right>card.right+1));
        }).map(el=>el.textContent.slice(0,50));
        const overflow=[...document.querySelectorAll('.panel')].filter(el=>el.scrollWidth>el.clientWidth+1)
          .map(el=>el.className);
        const wrapped=[...document.querySelectorAll('.left .kv span,.left .section-head h4,.left .title,.left .sub')]
          .filter(el=>{
            if(!el.getClientRects().length)return false;
            const range=document.createRange();range.selectNodeContents(el);
            const lines=new Set([...range.getClientRects()].map(rect=>Math.round(rect.top)));
            return lines.size>1||getComputedStyle(el).textOverflow==='ellipsis';
          }).map(el=>el.textContent.slice(0,50));
        const sections=[...document.querySelectorAll('.left .section')];
        const inaccessible=sections.filter(el=>el.scrollWidth>el.clientWidth+1&&
          !['auto','scroll'].includes(getComputedStyle(el).overflowX)).length;
        const blocked=[];
        for(const el of document.querySelectorAll('.left .kv span')) {
          if(!el.getClientRects().length||!el.firstChild?.textContent)continue;
          const section=el.closest('.section'),initial=section.scrollLeft;
          for(const end of [false,true]) {
            const text=el.firstChild,range=document.createRange(),offset=end?text.textContent.length-1:0;
            range.setStart(text,offset);range.setEnd(text,offset+1);
            const box=range.getBoundingClientRect(),viewport=section.getBoundingClientRect();
            section.scrollLeft+=end?Math.max(0,box.right-viewport.right+2):Math.min(0,box.left-viewport.left-2);
            const visible=range.getBoundingClientRect();
            if(visible.left<viewport.left-1||visible.right>viewport.right+1)blocked.push(el.textContent.slice(0,30));
          }
          section.scrollLeft=initial;
        }
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
      assert.equal(await pane.locator('.record').first().locator('a').isVisible(),true);
      await layout(label+' awards');
      await page.locator('.tab[data-tab="overview"]').click();
    }

    for(const width of [1440,1280,1024,768,390]) {
      await page.setViewportSize({width,height:900});
      await layout(width+'px path details');
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
    await page.locator('#workspaceOpen').click();
    const dialog=page.locator('dialog[open]');
    assert.equal(await dialog.count(),1);
    assert.equal(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
    assert.deepEqual(errors,[]);
    console.log('Panel layout: single-line source text, local horizontal scrolling, all awards in investigation/indexed/path modes, official lookup tabs, async updates, Workspace and 1440/1280/1024/768/390px passed.');
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
