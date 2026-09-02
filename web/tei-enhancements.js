/* T.E.I. UI enhancements: force-readable graph labels + company website/domain cross-check. */
(function(){
  const WHITE='#ffffff', STROKE='#070a0f';
  let current=null, lastUniform=null, busy=false;

  const style=document.createElement('style');
  style.textContent=`
    .graph svg text,.graph svg .node text,.graph svg text.node-label{fill:${WHITE}!important;color:${WHITE}!important;stroke:${STROKE}!important;stroke-width:4px!important;paint-order:stroke!important;user-select:none!important;-webkit-user-select:none!important}
    .tei-site-card{border:1px solid #2f4050;background:#0c131b;border-radius:8px;padding:10px;margin-top:9px;font-size:9px;color:#9aa8b7}
    .tei-site-card h4{margin:0 0 7px;color:#eaf0f6;font-size:10px}
    .tei-site-card .line{display:flex;justify-content:space-between;gap:10px;margin:6px 0;line-height:1.5}
    .tei-site-card .ok{color:#72d6a1}.tei-site-card .bad{color:#f04f5f}.tei-site-card .warn{color:#f2c56a}
    .tei-site-card a{color:#91baff;text-decoration:none}.tei-site-card code{font-family:ui-monospace,monospace;color:#d6dee7}
  `;
  document.head.appendChild(style);

  function forceWhite(){
    document.querySelectorAll('.graph svg text,.graph svg .node text,.graph svg text.node-label').forEach(t=>{
      t.setAttribute('fill',WHITE);
      t.setAttribute('stroke',STROKE);
      t.setAttribute('stroke-width','4');
      t.setAttribute('paint-order','stroke');
      t.style.setProperty('fill',WHITE,'important');
      t.style.setProperty('color',WHITE,'important');
      t.style.setProperty('stroke',STROKE,'important');
      t.style.setProperty('stroke-width','4px','important');
      t.style.setProperty('paint-order','stroke','important');
      t.style.setProperty('user-select','none','important');
    });
  }

  function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

  function renderWebsiteCheck(x){
    const pane=document.getElementById('overviewPane');
    if(!pane || !x?.uniform_number || document.getElementById('tei-site-card')) return;
    fetch('/api/website-check?uniform='+encodeURIComponent(x.uniform_number)+'&t='+Date.now(),{cache:'no-store'})
      .then(r=>r.json())
      .then(data=>{
        const site=data.website||{};
        const af=data.anti_fraud||{};
        const matches=Array.isArray(af.records)?af.records:[];
        const card=document.createElement('div');
        card.id='tei-site-card'; card.className='tei-site-card';
        const siteHtml=site.url
          ? `<div class="line"><span>公司網站</span><span><a href="${esc(site.url)}" target="_blank" rel="noreferrer">${esc(site.url)}</a></span></div>
             <div class="line"><span>網址來源</span><span>${esc(site.source||'—')}</span></div>`
          : `<div class="line"><span>公司網站</span><span>沒有可驗證的政府來源網址</span></div>
             <div class="line"><span>候選搜尋</span><span><a href="${esc(site.search_url||'#')}" target="_blank" rel="noreferrer">搜尋官方網站 ↗</a></span></div>`;
        const verdict=Number(af.matched||0)>0
          ? `<span class="bad">命中 ${Number(af.matched)} 筆政府詐騙網域資料</span>`
          : `<span class="ok">未命中目前檢查的政府詐騙網域資料</span>`;
        const detail=matches.length
          ? `<div style="margin-top:7px">${matches.slice(0,5).map(m=>`<div style="margin-top:6px"><code>${esc(m['網域名稱']||m['網址']||m.WEBURL||m.url||'')}</code><br>${esc(m.source_name||'政府公開資料')}</div>`).join('')}</div>`
          : '';
        card.innerHTML=`<h4>公司網站 × 165／MODA 詐騙網域交叉比對</h4>${siteHtml}<div class="line"><span>網域</span><span><code>${esc(data.domain||'—')}</code></span></div><div class="line"><span>比對結果</span><span>${verdict}</span></div>${detail}<div style="margin-top:7px;color:#748294;line-height:1.6">未命中不等於公司或網站獲得安全認定；這裡只表示該網域與本次檢查的政府公開詐騙網域資料是否相符。</div>`;
        pane.appendChild(card);
      })
      .catch(()=>{});
  }

  function refreshFromPage(){
    forceWhite();
    const q=document.getElementById('q');
    const uniform=q?.value?.trim();
    if(!/^\d{8}$/.test(uniform)) return;
    if(window.__tei_last_data) renderWebsiteCheck(window.__tei_last_data);
  }

  // Capture company API responses without changing the main app.
  const nativeFetch=window.fetch;
  window.fetch=function(...args){
    return nativeFetch.apply(this,args).then(r=>{
      try{
        const url=String(args[0]||'');
        if(url.includes('/api/company/')){
          r.clone().json().then(x=>{ current=x; window.__tei_last_data=x; renderWebsiteCheck(x); setTimeout(forceWhite,0); setTimeout(forceWhite,150); setTimeout(forceWhite,500); setTimeout(forceWhite,1200); }).catch(()=>{});
        }
      }catch(_){ }
      return r;
    });
  };

  const observer=new MutationObserver(()=>{ if(!busy){busy=true;forceWhite();setTimeout(()=>busy=false,0);} });
  observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['style','fill','stroke','class']});
  document.addEventListener('DOMContentLoaded',()=>{forceWhite();refreshFromPage();});
  setInterval(forceWhite,1500);
})();
