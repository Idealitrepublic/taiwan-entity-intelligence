APP_JS = r'''const $ = (id) => document.getElementById(id);
let state = { data: null, zoom: 1, panX: 0, panY: 0 };

function esc(v) {
  return String(v ?? "").replace(/[&<>\"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

function fmt(v) {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

function sourceClass(s) {
  return s === "ok" ? "ok" : s === "partial" ? "partial" : s === "error" ? "bad" : "off";
}

function sourceLabel(s) {
  if (!s) return "未查詢";
  if (s.status === "ok") return `${Number(s.matched || 0)} 筆`;
  if (s.status === "partial") return "部分可用";
  if (s.status === "not_configured") return "未設定";
  if (s.status === "not_available_in_public_runtime") return "公開環境不可用";
  return "查詢失敗";
}

function setSystemStatus(ok, text) {
  const el = $("systemStatus");
  if (!el) return;
  el.textContent = `● ${text}`;
  el.className = `status${ok ? "" : " off"}`;
}

async function loadStatus() {
  try {
    const r = await fetch(`/api/status?ts=${Date.now()}`, { cache: "no-store" });
    const x = await r.json();
    const db = $("dbStatus");
    if (db && x.supabase && x.supabase.configured) {
      db.innerHTML = `
        <div class="src"><span class="name">source_files</span><span class="ok">${x.supabase.source_files.toLocaleString()} 筆</span></div>
        <div class="src"><span class="name">companies</span><span class="${x.supabase.companies ? "ok" : "off"}">${x.supabase.companies.toLocaleString()} 筆</span></div>
        <div class="src"><span class="name">people</span><span class="${x.supabase.people ? "ok" : "off"}">${x.supabase.people.toLocaleString()} 筆</span></div>
        <div class="src"><span class="name">evidence</span><span class="${x.supabase.evidence ? "ok" : "off"}">${x.supabase.evidence.toLocaleString()} 筆</span></div>`;
    } else if (db) {
      db.innerHTML = `<div class="notice">Supabase 資料層尚未在 Vercel 設定讀取金鑰；公開 API 仍可使用。</div>`;
    }
    setSystemStatus(true, "LIVE DATA");
  } catch (_) {
    setSystemStatus(false, "API OFFLINE");
  }
}

function renderCompany(x) {
  state.data = x;
  const empty = $("graphEmpty");
  if (empty) empty.style.display = "none";
  const c = x.company || {};
  const name = x.company_name || c.Company_Name || x.uniform_number;
  $("company").textContent = name;
  $("uniform").textContent = x.uniform_number;
  $("companyKV").innerHTML = `
    <div class="kv">
      <div><span>公司狀態</span><span>${esc(c.Company_Status_Desc || c.Case_Status_Desc || "—")}</span></div>
      <div><span>負責人</span><span>${esc(c.Responsible_Name || "—")}</span></div>
      <div><span>地址</span><span title="${esc(c.Company_Location || "")}">${esc(c.Company_Location || "—")}</span></div>
      <div><span>設立日期</span><span>${esc(c.Company_Setup_Date || "—")}</span></div>
    </div>`;

  const statuses = x.evidence_status || {};
  $("sourceStatus").innerHTML = Object.entries(statuses).map(([k,v]) => `
    <div class="src"><span class="name">${esc(k)}</span><span class="${sourceClass(v?.status)}">${esc(sourceLabel(v))}</span></div>
  `).join("") || `<div class="notice">目前沒有額外來源回應。</div>`;

  const people = Array.isArray(x.people) ? x.people : [];
  const evidence = Array.isArray(x.evidence) ? x.evidence : [];
  $("people").textContent = people.length;
  $("edges").textContent = (x.graph?.edges || []).length;
  $("evcount").textContent = evidence.length;
  $("localev").textContent = Number(x.local_context?.evidence_count || 0);

  const hits = [];
  if (x.local_context?.company) hits.push("Supabase 公司資料");
  if (x.local_context?.evidence_count) hits.push(`${x.local_context.evidence_count} 筆既有證據`);
  $("signal").style.display = "block";
  $("signal").innerHTML = hits.length
    ? `<b>你的資料庫命中</b><br>${hits.map(esc).join("<br>")}`
    : `<b>目前資料層</b><br>本企業尚無結構化 Supabase evidence；以下內容以即時公開資料為主。`;

  $("graphTitle").textContent = name;
  $("graphSub").textContent = `統編 ${x.uniform_number} · ${people.length} 位董監事 · ${evidence.length} 筆來源證據`;
  renderOverview(x);
  renderEvidence(evidence);
  drawGraph(x.graph || {nodes:[],edges:[]});
}

function renderOverview(x) {
  const p = Array.isArray(x.people) ? x.people : [];
  $("overviewPane").innerHTML = `
    <div class="detail">
      <h3>${esc(x.company_name || x.uniform_number)}</h3>
      <div class="tag">Company · ${esc(x.uniform_number)}</div>
      <div class="card"><h4>資料來源</h4><p>經濟部商工行政資料開放平台</p><div class="meta"><span>即時 API</span><span>官方公開資料</span></div></div>
      <div class="card"><h4>董監事</h4>${p.length ? p.slice(0,30).map(r => `<p style="margin:7px 0"><b style="color:#e1e7ed">${esc(r.person_name)}</b> · ${esc(r.position || "職稱未提供")}</p>`).join("") : '<p>目前沒有讀到董監事資料。</p>'}</div>
      <div class="card local"><h4>我的 Supabase 資料</h4><p>${Number(x.local_context?.evidence_count || 0)} 筆 evidence 命中此統編。尚未命中的部分不會被系統假造。</p></div>
      <div class="notice">${esc(x.evidence_note || "來源資料僅代表觀測到的公開紀錄，不構成法律結論。")}</div>
      <p style="margin-top:10px;font-size:9px"><a href="${esc(x.judicial_search_url || "#")}" target="_blank" rel="noreferrer" style="color:#91baff;text-decoration:none">前往司法院裁判書系統搜尋 ↗</a></p>
    </div>`;
}

function renderEvidence(rows) {
  if (!rows.length) {
    $("evidencePane").innerHTML = `<div class="empty">目前沒有可直接呈現的 evidence。<br><br>查詢仍會顯示官方即時來源狀態。</div>`;
    return;
  }
  $("evidencePane").innerHTML = rows.map((e) => {
    const src = e.source?.name || e.source_type || "來源";
    const title = e.fact?.title || e.title || "來源紀錄";
    const summary = e.fact?.summary || e.summary || "";
    const url = e.source_url || e.source?.url || "";
    return `<div class="card"><h4>${esc(title)}</h4><p>${esc(summary)}</p><div class="meta"><span>${esc(src)}</span><span>${esc(e.event_date || e.observed_at || "")}</span></div>${url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">查看來源 ↗</a>` : ""}</div>`;
  }).join("");
}

function drawGraph(graph) {
  const svg = $("svg");
  if (!svg) return;
  svg.innerHTML = "";
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  if (!nodes.length) return;
  const width = 1000, height = 700;
  const cx = width/2, cy = height/2;
  const center = nodes.find(n => n.type === "company") || nodes[0];
  const others = nodes.filter(n => n.id !== center.id);
  const pos = new Map();
  pos.set(center.id, {x:cx,y:cy});
  const radius = Math.min(250, 80 + others.length*6);
  others.forEach((n,i) => {
    const a = (-Math.PI/2) + (i/Math.max(1,others.length))*Math.PI*2;
    pos.set(n.id,{x:cx+Math.cos(a)*radius,y:cy+Math.sin(a)*radius});
  });
  const g = document.createElementNS("http://www.w3.org/2000/svg","g");
  g.setAttribute("transform", `translate(${state.panX} ${state.panY}) scale(${state.zoom})`);
  svg.appendChild(g);
  edges.forEach(e => {
    const a=pos.get(e.source), b=pos.get(e.target); if(!a||!b)return;
    const line=document.createElementNS("http://www.w3.org/2000/svg","line");
    line.setAttribute("x1",a.x); line.setAttribute("y1",a.y); line.setAttribute("x2",b.x); line.setAttribute("y2",b.y); line.setAttribute("class","edge"); g.appendChild(line);
    if(e.relationship){const t=document.createElementNS("http://www.w3.org/2000/svg","text");t.setAttribute("x",(a.x+b.x)/2);t.setAttribute("y",(a.y+b.y)/2-5);t.setAttribute("class","edgeLabel");t.textContent=e.relationship;g.appendChild(t)}
  });
  nodes.forEach(n => {
    const p=pos.get(n.id); if(!p)return;
    const group=document.createElementNS("http://www.w3.org/2000/svg","g"); group.setAttribute("class","node"); group.dataset.id=n.id;
    const c=document.createElementNS("http://www.w3.org/2000/svg","circle"); c.setAttribute("cx",p.x); c.setAttribute("cy",p.y); c.setAttribute("r", n.id===center.id?30:17); c.setAttribute("fill", n.type==='company'?'#7fb0ff':n.type==='person'?'#63d39f':'#f2c56a'); group.appendChild(c);
    const t=document.createElementNS("http://www.w3.org/2000/svg","text"); t.setAttribute("x",p.x); t.setAttribute("y",p.y+(n.id===center.id?48:34)); t.setAttribute("text-anchor","middle"); t.textContent=n.label || n.id; group.appendChild(t);
    group.addEventListener("click",()=>selectNode(n)); g.appendChild(group);
  });
}

function selectNode(n) {
  $("overviewPane").innerHTML = `<div class="detail"><h3>${esc(n.label || n.id)}</h3><div class="tag">${esc(n.type || "node")}</div><div class="card"><h4>節點屬性</h4><p>${esc(JSON.stringify(n.properties || {}, null, 2))}</p></div><div class="notice">此節點來自公開來源查詢。關係本身不代表犯罪、控制或不當行為。</div></div>`;
}

async function searchCompany() {
  const q = $("q");
  const search = $("search");
  if (!q || !search) return;
  const value = q.value.trim();
  if(!/^\d{8}$/.test(value)) { q.focus(); return; }
  search.disabled=true; search.textContent="查詢中…";
  try {
    const r=await fetch(`/api/company/${value}?ts=${Date.now()}`, {cache:"no-store"});
    const x=await r.json();
    if(!r.ok) throw new Error(x.error || "查詢失敗");
    renderCompany(x);
  } catch(e) {
    $("company").textContent="查詢失敗"; $("uniform").textContent=e.message;
    $("graphEmpty").style.display="grid"; $("graphEmpty").innerHTML=`查詢失敗<br>${esc(e.message)}`;
  } finally { search.disabled=false; search.textContent="開始調查"; }
}

document.addEventListener("DOMContentLoaded", () => {
  $("search")?.addEventListener("click", searchCompany);
  $("q")?.addEventListener("keydown", e => { if(e.key === "Enter") searchCompany(); });
  $("sample")?.addEventListener("click",()=>{ $("q").value="20828393"; searchCompany(); });
  $("clear")?.addEventListener("click",()=>{ state={data:null,zoom:1,panX:0,panY:0}; $("svg").innerHTML=""; $("graphEmpty").style.display="grid"; $("company").textContent="尚未選擇企業"; $("uniform").textContent="輸入統編開始調查"; });
  $("fit")?.addEventListener("click",()=>{state.zoom=1;state.panX=0;state.panY=0;if(state.data)drawGraph(state.data.graph||{nodes:[],edges:[]});});
  $("plus")?.addEventListener("click",()=>{state.zoom=Math.min(2.5,state.zoom+0.2);if(state.data)drawGraph(state.data.graph||{nodes:[],edges:[]});});
  $("minus")?.addEventListener("click",()=>{state.zoom=Math.max(.6,state.zoom-.2);if(state.data)drawGraph(state.data.graph||{nodes:[],edges:[]});});
  $("one")?.addEventListener("click",()=>{state.zoom=1;if(state.data)drawGraph(state.data.graph||{nodes:[],edges:[]});});
  document.querySelectorAll(".tab").forEach(btn=>btn.addEventListener("click",()=>{
    document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active")); btn.classList.add("active");
    const tab=btn.dataset.tab; $("overviewPane").style.display=tab==='overview'?"block":"none"; $("evidencePane").style.display=tab==='evidence'?"block":"none";
  }));
  loadStatus();
});
'''
