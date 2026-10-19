# Development report presentation acceptance — 2026-10-19

Scope: Development/Preview report presentation only. The JSON report projection,
Workspace ownership checks, publication filters, Entity/Relationship/Evidence
model, and Production are unchanged.

The layout takes the *pattern* of a compact investigation summary, grouped
findings, provenance register, and explicit coverage caveats from international
public-record investigation tools (such as OpenCorporates and OCCRP Aleph), not
their branding or data. HTML and PDF now share one display-only projection:

1. Investigation title, methodology, generated time, three summary counts.
2. Saved items (Workspace only), Entity profiles, relationships, contracts,
   judgments, penalties, assets, graph scope, and sources, grouped by topic.
3. Each relationship includes its type, endpoints, date/amount when present,
   primary Evidence, source URL and retrieval time. Other source facts remain
   available in the unchanged JSON response.
4. Empty topics appear once at the end instead of repeating a full empty card.
   Truncation and unavailable saved references are flagged.

Local verification: 19 focused report/PDF tests passed; full repository tests,
lint and build passed. The generated sample PDF was rendered to an image and
inspected for landscape layout, Chinese glyphs, readable table columns, source
link and footer. Long Chinese/English strings and URLs remain covered by the
PDF regression tests. The sample is synthetic; a real signed-in Workspace PDF
and printout remain **unverified** until a Development test session is available.

Data and Pilot gates remain separate. The last dated Development coverage
baseline in `COMPANY_LINKAGE_ACCEPTANCE_2026-10-19.md` is 462 published,
exact-ID Companies and 1,028 evidence-backed published edges, but very few
published procurement/labor/political edges and no verified company-judgment
edges. A fresh read-only DB sample was attempted but could not complete in
this environment, so these figures are **not** claimed as current. Name-only
labor/judicial matches remain unpublished. Cross-account signed-in access and
the four real-user Pilot sessions remain **not run**; no fabricated result or
Production approval is inferred from this document.
