import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const site = "https://taiwan-entity-intelligence.vercel.app";
const headers = {
  "Access-Control-Allow-Origin": "*",
  "Cache-Control": "no-store",
};
const json = (body: unknown, status = 200) => Response.json(body, { status, headers });

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
  if (request.method !== "GET") return json({ status: "error", error: "Method not allowed" }, 405);
  const url = new URL(request.url);
  if (url.pathname.endsWith("/health")) {
    return json({ status: "ok", service: "tei-web", persist: false });
  }
  if (url.searchParams.get("api") !== "company") return Response.redirect(site, 302);
  const uniform = url.searchParams.get("uniform") ?? "";
  if (!/^\d{8}$/.test(uniform)) {
    return json({ status: "error", error: "統編必須為 8 碼數字" }, 400);
  }

  try {
    const response = await fetch(`${site}/api/company/${uniform}`, {
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) return json({ status: "error", error: "公司資料暫時無法讀取" }, response.status);
    const result = await response.json();
    const { company, company_name, people, graph, website_url, website_host, local_context, evidence_status } = result;
    const publicGraph = (graph?.nodes ?? []).filter(
      (node: { type: string }) => ["company", "person"].includes(node.type)
    );
    const visibleIds = new Set(publicGraph.map((node: { id: string }) => node.id));
    const edges = (graph?.edges ?? []).filter(
      (edge: { source: string; target: string }) => visibleIds.has(edge.source) && visibleIds.has(edge.target)
    );
    const context = {
      configured: Boolean(local_context?.configured),
      evidence_count: Array.isArray(local_context?.evidence) ?
        local_context.evidence.filter((record: { source_type: string }) =>
          ["moea_company", "moea_director"].includes(record.source_type)
        ).length : 0,
    };
    return json({
      status: "ok",
      uniform_number: uniform,
      company,
      company_name,
      people,
      graph: { nodes: publicGraph, edges },
      website: website_url ? { url: website_url, host: website_host } : null,
      domain: website_host,
      local_context: context,
      persistence: { status: "disabled" },
      evidence_status: {
        "公司登記": evidence_status?.["公司登記"],
        "董監事": evidence_status?.["董監事"],
        "165": evidence_status?.["165"],
      },
    });
  } catch {
    return json({ status: "error", error: "公司資料暫時無法讀取" }, 502);
  }
});
