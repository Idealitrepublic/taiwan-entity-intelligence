const $ = (id) => document.getElementById(id);
let state = { data: null, zoom: 1, panX: 0, panY: 0 };

function esc(v) {
  return String(v ?? "").replace(/[&<>\"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  }[c]));
}

function sourceClass(status) {
  if (status === "ok") return "ok";
  if (status === "partial" || status === "link") return "partial";
  if (status === "error") return "bad";
  return "off";
}

function sourceLabel(item) {
  if (!item) return "未查詢";
  const status = item.status;
  if (status === "ok") return `${Number(item.matched || 0)} 筆`;
  if (status === "partial") return "部分可用";
  if (status === "link") return "官方查詢入口";
  if (status === "not_configured") return "未設定";
  if (status === "not_available_in_public_runtime") return "公開環境不可用";
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
    if (x.supabase?.configured) {
      db.innerHTML = [
        ["source_files", x.supabase.source_files],
        ["companies", x.supabase.companies],
        ["people", x.supabase.people],
        ["evidence", x.supabase.evidence]
      ].map(([name, n]) => `<div class="src"><span class="name">${name}</span><span class="${n ? "ok" : "off"}">${Number(n || 0).toLocaleString()} 筆</span></div>`).join("");
    } else {
      db.innerHTML = `<div class="notice">Supabase 資料層尚未在 Vercel 設定讀取金鑰；公開 API 仍可使用。</div>`;
    }
    setSystemStatus(true, "LIVE DATA");
  } catch (e) {
    setSystemStatus(false, "API OFFLINE");
  }
}

function renderCompany(x) {
  state.data = x;
  const c = x.company || {};
  const name = x.company_name || c.Company_Name || x.uniform_number;
  $("graphEmpty").style.display = "none";
  $("company").textContent = name;
  $("uniform").textContent = x.uniform_number || "";
  $("companyKV").innerHTML = `<div class="kv">
    <div><span>公司狀態</span><span>${esc(c.Company_Status_Desc || c.Case_Status_Desc || "—")}</span></div>
    <div><span>負責人</span><span>${esc(c.Responsible_Name || "—")}</span></div>
    <div><span>地址</span><span>${esc(c.Company_Location || "—")}</span></div>
    <div><span>設立日期</span><span>${esc(c.Company_Setup_Date || "—")}</span></div>
  </div>`;

  const statuses = x.evidence_status || {};
  $("sourceStatus").innerHTML = Object.entries(statuses).map(([k, v]) => {
    const cls = sourceClass(v?.status);
    const label = sourceLabel(v);
    const right = v?.status === "link" && v?.url
      ? `<a class="${cls}" href="${esc(v.url)}" target="_blank" rel="noreferrer">${esc(label)} ↗</a>`
      : `<span class="${cls}">${esc(label)}</span>`;
    return `<div class="src"><span class="name">${esc(k)}</span>${right}</div>`;
  }).join("") || `<div class="notice">目前沒有額外來源回應。</div>`;

  const people = Array.isArray(x.people) ? x.people : [];
  const evidence = Array.isArray(x.evidence) ? x.evidence : [];
  $("people").textContent = people.length;
  $("edges").textContent = Array.isArray(x.graph?.edges) ? x.graph.edges.length : 0;
  $("evcount").textContent = evidence.length;
  $("localev").textContent = Number(x.local_context?.evidence_count || 0);

  const signal = $("signal");
  signal.style.display = "block";
  signal.innerHTML = x.local_context?.evidence_count
    ? `<b>你的資料庫命中</b><br>Supabase evidence ${Number(x.local_context.evidence_count).toLocaleString()} 筆`
    : `<b>目前資料層</b><br>本企業尚無結構化 Supabase evidence；以下內容以即時公開資料為主。`;

  $("graphTitle").textContent = name;
  $("graphSub").textContent = `統編 ${x.uniform_number} · ${people.length} 位董監事 · ${evidence.length} 筆來源證據`;
  renderOverview(x);
  renderEvidence(evidence);
  drawGraph(x.graph || { nodes: [], edges: [] });
}

function renderOverview(x) {
  const people = Array.isArray(x.people) ? x.people : [];
  $("overviewPane").innerHTML = `<div class="detail">
    <h3>${esc(x.company_name || x.uniform_number)}</h3>
    <div class="tag">Company · ${esc(x.uniform_number)}</div>
    <div class="card"><h4>資料來源</h4><p>經濟部商工行政資料開放平台</p><div class="meta"><span>即時 API</span><span>官方公開資料</span></div></div>
    <div class="card"><h4>董監事</h4>${people.length ? people.slice(0, 30).map((r) => `<p style="margin:7px 0"><b style="color:#e1e7ed">${esc(r.person_name)}</b> · ${esc(r.position || "職稱未提供")}</p>`).join("") : "<p>目前沒有讀到董監事資料。</p>"}</div>
    <div class="card local"><h4>我的 Supabase 資料</h4><p>${Number(x.local_context?.evidence_count || 0)} 筆 evidence 命中此統編。</p></div>
    <div class="notice">${esc(x.evidence_note || "公開來源僅供研究使用，請核對原始文件。")}</div>
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
  svg.innerHTML = "";
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  if (!nodes.length) return;

  const W = 1000, H = 700, cx = W / 2, cy = H / 2;
  const center = nodes.find((n) => n.type === "company") || nodes[0];
  const others = nodes.filter((n) => n.id !== center.id);
  const pos = new Map([[center.id, { x: cx, y: cy }]]);
  const radius = Math.min(250, 90 + others.length * 6);

  others.forEach((n, i) => {
    const a = -Math.PI / 2 + i / Math.max(1, others.length) * Math.PI * 2;
    pos.set(n.id, { x: cx + Math.cos(a) * radius, y: cy + Math.sin(a) * radius });
  });

  const ns = "http://www.w3.org/2000/svg";
  const g = document.createElementNS(ns, "g");
  g.setAttribute("transform", `translate(${state.panX} ${state.panY}) scale(${state.zoom})`);
  svg.appendChild(g);

  edges.forEach((e) => {
    const a = pos.get(e.source), b = pos.get(e.target);
    if (!a || !b) return;
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
    line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
    line.setAttribute("class", "edge");
    g.appendChild(line);
  });

  nodes.forEach((n) => {
    const p = pos.get(n.id);
    if (!p) return;
    const group = document.createElementNS(ns, "g");
    group.setAttribute("class", "node");
    const circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", p.x); circle.setAttribute("cy", p.y);
    circle.setAttribute("r", n.id === center.id ? 30 : 17);
    circle.setAttribute("fill", n.type === "company" ? "#7fb0ff" : n.type === "person" ? "#63d39f" : "#f2c56a");
    group.appendChild(circle);

    const text = document.createElementNS(ns, "text");
    text.setAttribute("x", p.x); text.setAttribute("y", p.y + (n.id === center.id ? 48 : 34));
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "#ffffff");
    text.setAttribute("stroke", "#070a0f");
    text.setAttribute("stroke-width", "4");
    text.setAttribute("paint-order", "stroke");
    text.setAttribute("font-size", "11");
    text.textContent = n.label || n.id;
    group.appendChild(text);

    group.addEventListener("click", () => selectNode(n));
    g.appendChild(group);
  });
}

function selectNode(n) {
  $("overviewPane").innerHTML = `<div class="detail"><h3>${esc(n.label || n.id)}</h3><div class="tag">${esc(n.type || "node")}</div><div class="card"><h4>節點屬性</h4><pre style="white-space:pre-wrap;color:#9eabb9;font-size:9px">${esc(JSON.stringify(n.properties || {}, null, 2))}</pre></div><div class="notice">此節點來自公開來源查詢。關係本身不代表犯罪、控制或不當行為。</div></div>`;
}

async function searchCompany() {
  const q = $("q").value.trim();
  if (!/^\d{8}$/.test(q)) { $("q").focus(); return; }
  $("search").disabled = true;
  $("search").textContent = "查詢中…";
  try {
    const r = await fetch(`/api/company/${q}?ts=${Date.now()}`, { cache: "no-store" });
    const x = await r.json();
    if (!r.ok) throw new Error(x.error || "查詢失敗");
    renderCompany(x);
  } catch (e) {
    $("company").textContent = "查詢失敗";
    $("uniform").textContent = e.message;
    $("graphEmpty").style.display = "grid";
    $("graphEmpty").textContent = `查詢失敗\n${e.message}`;
  } finally {
    $("search").disabled = false;
    $("search").textContent = "開始調查";
  }
}

$("search").addEventListener("click", (e) => { e.preventDefault(); searchCompany(); });
$("q").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); searchCompany(); } });
$("sample").addEventListener("click", (e) => { e.preventDefault(); $("q").value = "96972256"; searchCompany(); });
$("clear").addEventListener("click", () => { state = { data: null, zoom: 1, panX: 0, panY: 0 }; $("svg").innerHTML = ""; $("graphEmpty").style.display = "grid"; $("company").textContent = "尚未選擇企業"; $("uniform").textContent = "輸入統編開始調查"; });
$("fit").addEventListener("click", () => { state.zoom = 1; state.panX = 0; state.panY = 0; if (state.data) drawGraph(state.data.graph || { nodes: [], edges: [] }); });
$("plus").addEventListener("click", () => { state.zoom = Math.min(2.5, state.zoom + 0.2); if (state.data) drawGraph(state.data.graph || { nodes: [], edges: [] }); });
$("minus").addEventListener("click", () => { state.zoom = Math.max(0.6, state.zoom - 0.2); if (state.data) drawGraph(state.data.graph || { nodes: [], edges: [] }); });
$("one").addEventListener("click", () => { state.zoom = 1; if (state.data) drawGraph(state.data.graph || { nodes: [], edges: [] }); });
document.querySelectorAll(".tab").forEach((btn) => btn.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
  btn.classList.add("active");
  const tab = btn.dataset.tab;
  $("overviewPane").style.display = tab === "overview" ? "block" : "none";
  $("evidencePane").style.display = tab === "evidence" ? "block" : "none";
}));

loadStatus();
