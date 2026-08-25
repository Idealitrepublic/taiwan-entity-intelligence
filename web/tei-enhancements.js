/* T.E.I. demo enhancements: risk signals + plain-language evidence. */
(function(){
  const style=document.createElement('style');
  style.textContent='.tei-risk-ring{fill:none;stroke:#f47c8b;stroke-width:3;opacity:.95;filter:drop-shadow(0 0 5px rgba(244,124,139,.45))}.tei-translation{margin-top:8px;padding:8px;border-left:2px solid #f4c96b;background:#13130f;color:#d9d1bd;font-size:10px;line-height:1.65}.tei-risk-note{color:#f4c96b;font-size:9px;line-height:1.5;margin-top:6px}';
  document.head.appendChild(style);
  let lastPayload=null,lastUrl=null;
  function plainLanguage(ev){
    let text=String((((ev||{}).fact||{}).summary)||(((ev||{}).fact||{}).title)||'').trim();
    [['人頭負責人','以他人名義掛名當公司負責人'],['人頭股東','以他人名義掛名當股東'],['詐欺集團','判決書描述的詐騙犯罪集團'],['對21人實施詐欺','涉及對 21 名被害人進行詐騙'],['判決記載','法院判決中記載'],['應以裁判全文核對','仍要以完整判決的主文與理由確認']].forEach(([a,b])=>text=text.split(a).join(b));
    return text;
  }
  function riskMap(p){const m={};(p.evidence||[]).forEach(e=>{const id=e.entity_id,s=String((e.source||{}).name||'');if(id&&/裁判|法院|詐欺|反詐|涉詐|裁罰|處分|違法/.test(s))m[id]=1});return m}
  function paint(p){const risk=riskMap(p);document.querySelectorAll('#canvas g.node').forEach(g=>{const label=(g.textContent||'').trim(),n=(p.graph?.nodes||[]).find(x=>String(x.label||'')===label);if(!n||!risk[n.id])return;const c=g.querySelector('circle');if(!c||g.querySelector('.tei-risk-ring'))return;const r=document.createElementNS('http://www.w3.org/2000/svg','circle');r.setAttribute('r',parseFloat(c.getAttribute('r')||'14')+5);r.setAttribute('class','tei-risk-ring');r.setAttribute('pointer-events','none');g.insertBefore(r,c)})}
  function plain(p){const pane=document.getElementById('evidencePane');if(!pane)return;const cards=pane.querySelectorAll('.evidence-card');(p.evidence||[]).forEach((e,i)=>{const card=cards[i],t=plainLanguage(e);if(card&&t&&!card.querySelector('.tei-translation')){const b=document.createElement('div');b.className='tei-translation';b.innerHTML='<b>白話解讀：</b> '+t.replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));card.appendChild(b)}});if(!pane.querySelector('.tei-risk-note')){const n=document.createElement('div');n.className='tei-risk-note';n.textContent='紅色＝公開司法／裁罰／反詐資料命中的風險訊號，不代表系統認定該人或公司有罪；請以原始資料確認。';pane.appendChild(n)}}
  async function refresh(){const i=document.getElementById('uniform'),id=i&&i.value.trim();if(!/^\d{8}$/.test(id))return;const u='/api/company/'+id;if(lastUrl===u)return;lastUrl=u;try{const r=await fetch(u),p=await r.json();if(!r.ok)return;lastPayload=p;[300,900,1700].forEach(ms=>setTimeout(()=>{paint(p);plain(p)},ms))}catch(e){}}
  document.addEventListener('click',e=>{if(e.target&&(e.target.id==='search'||e.target.id==='demo')){lastUrl=null;setTimeout(refresh,700)}});
  new MutationObserver(()=>{if(lastPayload){paint(lastPayload);plain(lastPayload)}}).observe(document.body,{subtree:true,childList:true,characterData:true});
})();
