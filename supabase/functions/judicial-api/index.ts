import "jsr:@supabase/functions-js/edge-runtime.d.ts";

Deno.serve(() => Response.json(
  {status: "withdrawn", message: "此資料已停止公開查詢 / Public lookup withdrawn"},
  {status: 410, headers: {"Cache-Control": "no-store"}}
));
