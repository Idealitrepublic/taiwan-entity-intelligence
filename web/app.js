const $ = (id) => document.getElementById(id);
let state = { data: null, zoom: 1 };

function esc(v) {
  return String(v ?? "").replace(/[&<>\"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}
function n(v) { const x = Number(v); return Number.isFinite(x) ? x : 0; }
function statusClass(s) { return s === "ok" ? "ok" : (s === "partial" || s === "link" ? "partial" : (s === "not_configured" || s === "no_website" ? "off" : "bad")); }
function statusLabel(v) {
  if (!v) return "未查詢";
  if (v.status === "ok") return `${n(v.matched)} 筆`;
  if (v.status === "partial") return v.message || "部分可用";
  if (v.status === "link") return "官方查詢入口";
  if (v.status === "no_website") return "未取得公司網址";
  if (v.status === "not_configured") return "未設定";
  return "查詢失敗";
}
function sourceRow(name, value) {
  const cls = statusClass(value?.status);
  const label = statusLabel(value);
  const link = value?.url ? ` <a class="${cls}" href="${esc(value.url)}" target="_blank" rel="noreferrer">↗</a>` : "";
  return `<div class="src"><span class="name">${esc(name)}</span><span class="${cls}">${esc(label)}${link}</span></div>`;
}

async function loadStatus() {
  try {
    const r = await fetch(`/api/status?ts=${Date.now()}`, { cache: "no-store" });
    const x = await r.json();
    if (x.supabase?.configured) {
      $("dbStatus").innerHTML = ["source_files","companies","people","evidence"].map(k =>
        `<div class="src"><span class="name">${k}</span><span class="${n(x.supabase[k]) ? "ok" : "off"}">${n(x.supabase[k]).toLocaleString()} 筆</span></div>`).join("");
    } else {
      $("dbStatus").innerHTML = `<div class="notice">Supabase 資料層未設定公開讀取金鑰。</div>`;
    }
    $("systemStatus").textContent = "● LIVE DATA";
    $("systemStatus").className = "status";
  } catch (e) {
    $("systemStatus").textContent = "● API OFFLINE";
    $("systemStatus").className = "status off";
  }
}

function renderCompany(x) {
  state.data = x;
  const c = x.company || {};
  const name = x.company_name || c.Company_Name || x.uniform_number;
  const people = Array.isArray(x.people) ? x.people : [];
  const evidence = Array.isArray(x.evidence) ? x.evidence : [];
  $("graphEmpty").style.display = "none";
  $("company").textContent = name;
  $("uniform").textContent = x.uniform_number || "";
  $("companyKV").innerHTML = `<div class="kv">
    <div><span>公司狀態</span><span>${esc(c.Company_Status_Desc || c.Case_Status_Desc || "—")}</span></div>
    <div><span>負責人</span><span>${esc(c.Responsible_Name || "—")}</span></div>
    <div><span>地址</span><span title="${esc(c.Company_Location || "")}">${esc(c.Company_Location || "—")}</span></div>
    <div><span>設立日期</span><span>${esc(c.Company_Setup_Date || "—")}</span></div>
    <div><span>公司網址</span><span>${x.website_url ? `<a href="${esc(x.website_url)}" target="_blank" rel="noreferrer">${esc(x.website_host || x.website_url)} ↗</a>` : "—"}</span></div>
  </div>`;

  const statuses = x.evidence_status || {};
  $("sourceStatus").innerHTML = Object.entries(statuses).map(([k,v]) => sourceRow(k,v)).join("") || `<div class="notice">目前沒有額外來源回應。</div>`;
  $("people").textContent = people.length;
  $("edges").textContent = Array.isArray(x.graph?.edges) ? x.graph.edges.length : 0;
  $("evcount").textContent = evidence.length;
  $("localev").textContent = n(x.local_context?.evidence_count);
  $("signal").style.display = "block";
  $("signal").innerHTML = x.local_context?.evidence_count
    ? `<b>你的資料庫命中</b><br>Supabase evidence ${n(x.local_context.evidence_count).toLocaleString()} 筆`
    : `<b>目前資料層</b><br>本企業尚無結構化 Supabase evidence；其餘內容來自即時公開來源。`;

  $("graphTitle").textContent = name;
  $("graphSub").textContent = `統編 ${x.uniform_number} · ${people.length} 位董監事 · ${evidence.length} 筆來源證據`;
  renderOverview(x);
  renderEvidence(evidence, x);
  drawGraph(x.graph || {nodes:[], edges:[]});
}

function renderOverview(x) {
  const people = Array.isArray(x.people) ? x.people : [];
  const c = x.company || {};
  const name = x.company_name || x.uniform_number;
  $("overviewPane").innerHTML = `<div class="detail">
    <h3>${esc(name)}</h3><div class="tag">Company · ${esc(x.uniform_number)}</div>
    <div class="card"><h4>公司基本資料</h4><p>來源：經濟部商工行政資料開放平台</p><div class="meta"><span>即時 API</span><span>官方公開資料</span></div></div>
    <div class="card"><h4>董監事</h4>${people.length ? people.slice(0,40).map(r => `<p style="margin:7px 0"><b>${esc(r.person_name)}</b> · ${esc(r.position || "職稱未提供")}</p>`).join("") : "<p>目前沒有讀到董監事資料。</p>"}</div>
    <div class="card"><h4>公司網址</h4><p>${x.website_url ? `<a href="${esc(x.website_url)}" target="_blank" rel="noreferrer">${esc(x.website_url)}</a>` : "經濟部公司資料未提供可交叉比對的公司網址。"}</p></div>
    <div class="card local"><h4>我的 Supabase 資料</h4><p>${n(x.local_context?.evidence_count)} 筆 evidence 命中此統編。</p></div>
    <div class="notice">${esc(x.evidence_note || "公開來源僅供研究使用，請核對原始文件。")}</div>
    <p style="margin-top:10px;font-size:9px"><a href="${esc(x.judicial_search_url || "#")}" target="_blank" rel="noreferrer" style="color:#91baff;text-decoration:none">前往司法院裁判書系統搜尋 ↗</a></p>
  </div>`;
}

function renderEvidence(rows, x) {
  const cross = x.website_crosscheck || {};
  const crossHtml = `<div class="card ${cross.status === "ok" && n(cross.matched) ? "risk-bad" : ""}">
    <h4>公司網址 × 165 反詐騙網域交叉比對</h4>
    <p><b>公司網址：</b>${cross.website_url ? `<a href="${esc(cross.website_url)}" target="_blank" rel="noreferrer">${esc(cross.website_host || cross.website_url)} ↗</a>` : "未取得"}</p>
    <p style="margin-top:6px"><b>比對結果：</b>${esc(cross.message || statusLabel(cross))}</p>
    ${Array.isArray(cross.records) && cross.records.length ? `<div class="meta"><span>命中 ${cross.records.length} 筆</span><span>精確網域 / 子網域規則</span></div>` : ""}
  </div>`;
  if (!rows.length) {
    $("evidencePane").innerHTML = crossHtml + `<div class="empty">目前沒有可直接呈現的其他 evidence。<br><br>上方仍會顯示來源狀態與網址交叉比對。</div>`;
    return;
  }
  $("evidencePane").innerHTML = crossHtml + rows.map((e) => {
    const src = e.source?.name || e.source_type || "來源";
    const title = e.fact?.title || e.title || "來源紀錄";
    const summary = e.fact?.summary || e.summary || "";
    const url = e.source_url || e.source?.url || "";
    return `<div class="card"><h4>${esc(title)}</h4><p>${esc(summary)}</p><div class="meta"><span>${esc(src)}</span><span>${esc(e.event_date || e.observed_at || "")}</span></div>${url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">查看來源 ↗</a>` : ""}</div>`;
  }).join("");
}

function drawGraph(graph) {
  const svg = $("svg");
  svg.innerHTML = "";
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  if (!nodes.length) return;
  const W = 1000, H = 700, cx = 500, cy = 350;
  const center = nodes.find(n => n.type === "company") || nodes[0];
  const others = nodes.filter(n => n.id !== center.id);
  const pos = new Map([[center.id, {x:cx, y:cy}]]);
  const radius = Math.min(285, 90 + others.length * 7);
  others.forEach((node,i) => { const a = -Math.PI/2 + i/Math.max(1,others.length)*Math.PI*2; pos.set(node.id,{x:cx+Math.cos(a)*radius,y:cy+Math.sin(a)*radius}); });
  const ns = "http://www.w3.org/2000/svg";
  const root = document.createElementNS(ns,"g");
  root.setAttribute("transform",`scale(${state.zoom})`);
  svg.appendChild(root);
  edges.forEach(e => {
    const a=pos.get(e.source), b=pos.get(e.target); if(!a||!b)return;
    const line=document.createElementNS(ns,"line"); line.setAttribute("x1",a.x); line.setAttribute("y1",a.y); line.setAttribute("x2",b.x); line.setAttribute("y2",b.y); line.setAttribute("class","edge"); root.appendChild(line);
  });
  nodes.forEach(node => {
    const p=pos.get(node.id); if(!p)return;
    const group=document.createElementNS(ns,"g"); group.setAttribute("class","node");
    const circle=document.createElementNS(ns,"circle"); circle.setAttribute("cx",p.x); circle.setAttribute("cy",p.y); circle.setAttribute("r",node.id===center.id?31:18); circle.setAttribute("fill",node.type==='company'?'#7fb0ff':node.type==='person'?'#63d39f':'#f2c56a'); group.appendChild(circle);
    const text=document.createElementNS(ns,"text"); text.setAttribute("x",p.x); text.setAttribute("y",p.y+(node.id===center.id?48:34)); text.setAttribute("text-anchor","middle"); text.setAttribute("fill","#fff"); text.setAttribute("stroke","#070a0f"); text.setAttribute("stroke-width","4"); text.setAttribute("paint-order","stroke"); text.setAttribute("font-size","11"); text.textContent=node.label||node.id; group.appendChild(text);
    group.addEventListener("click",()=>selectNode(node)); root.appendChild(group);
  });
}
function selectNode(node) {
  $("overviewPane").innerHTML = `<div class="detail"><h3>${esc(node.label||node.id)}</h3><div class="tag">${esc(node.type||"node")}</div><div class="card"><h4>節點屬性</h4><pre style="white-space:pre-wrap;color:#9eabb9;font-size:9px">${esc(JSON.stringify(node.properties||{},null,2))}</pre></div><div class="notice">此節點來自公開來源查詢。關係本身不代表犯罪、控制或不當行為。</div></div>`;
}

async function searchCompany() {
  const q=$("q").value.trim();
  if(!/^\d{8}$/.test(q)){ $("q").focus(); return; }
  $("search").disabled=true; $("search").textContent="查詢中…";
  try{
    const r=await fetch(`/api/company/${q}?ts=${Date.now()}`,{cache:"no-store"});
    const x=await r.json(); if(!r.ok) throw new Error(x.error||"查詢失敗");
    renderCompany(x);
  }catch(e){
    $("company").textContent="查詢失敗"; $("uniform").textContent=e.message; $("graphEmpty").style.display="grid"; $("graphEmpty").innerHTML=`查詢失敗<br>${esc(e.message)}`;
  }finally{ $("search").disabled=false; $("search").textContent="開始調查"; }
}

document.addEventListener("DOMContentLoaded",()=>{
  $("search")?.addEventListener("click",searchCompany);
  $("q")?.addEventListener("keydown",e=>{if(e.key==="Enter")searchCompany();});
  $("sample")?.addEventListener("click",()=>{$("q").value="96972256";searchCompany();});
  $("clear")?.addEventListener("click",()=>{state={data:null,zoom:1};$("svg").innerHTML="";$("graphEmpty").style.display="grid";$("company").textContent="尚未選擇企業";$("uniform").textContent="輸入統編開始調查";});
  $("fit")?.addEventListener("click",()=>{state.zoom=1;if(state.data)drawGraph(state.data.graph||{nodes:[],edges:[]});});
  $("plus")?.addEventListener("click",()=>{state.zoom=Math.min(2.5,state.zoom+.2);if(state.data)drawGraph(state.data.graph||{nodes:[],edges:[]});});
  $("minus")?.addEventListener("click",()=>{state.zoom=Math.max(.6,state.zoom-.2);if(state.data)drawGraph(state.data.graph||{nodes:[],edges:[]});});
  $("one")?.addEventListener("click",()=>{state.zoom=1;if(state.data)drawGraph(state.data.graph||{nodes:[],edges:[]});});
  document.querySelectorAll(".tab").forEach(btn=>btn.addEventListener("click",()=>{document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));btn.classList.add("active");const tab=btn.dataset.tab;$("overviewPane").style.display=tab==='overview'?"block":"none";$("evidencePane").style.display=tab==='evidence'?"block":"none";}));
  loadStatus();
});
