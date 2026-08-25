# Taiwan Entity Intelligence

Taiwan Entity Intelligence is an investigation-oriented MVP for turning Taiwanese public records into an explorable, source-backed entity relationship graph.

## Current direction

The product is moving from **data aggregation** to **cross-source evidence intelligence**:

**Entity → Relationship → Evidence → Cross-source verification → Signal → Investigation**

The first evidence domains are:

- Company / director registry
- Government procurement / tenders
- Judicial court records
- Government administrative penalties
- Government anti-fraud / fraud-warning signals

## Unified Evidence Schema

Every source-backed fact is normalized into the local `evidence` table. The schema keeps:

- `evidence_id` — deterministic identity of the source record + payload
- `source_type` / `source_name` — provenance domain and publisher/source
- `source_record_id` — original record identifier
- `source_url` — original source when available
- `source_published_at` / `observed_at` / `retrieved_at` — time provenance
- `entity_id` / `entity_type` — the entity the evidence concerns
- `fact_type` — observed fact category
- `relation_type` — relationship represented by the evidence
- `target_entity_id` / `target_entity_type` — optional related entity
- `title` / `summary` — human-readable context
- `confidence` — evidence quality score, not a probability of wrongdoing
- `status` — active / superseded / removed as the ingestion pipeline evolves
- `raw_payload_json` — original normalized record for auditability

The graph can attach `evidence_ids` to edges, so a relationship can be traced back to source records instead of being presented as an unexplained inference.

## Evidence ingestion

`src/ingest.py` supports CSV/JSON imports for four source classes:

```bash
python3 -m src.ingest judicial data/judicial.csv \
  --entity-field uniform_number \
  --record-id-field jid \
  --title-field title --date-field date --url-field url

python3 -m src.ingest procurement data/tenders.csv \
  --entity-field uniform_number \
  --record-id-field tender_id \
  --title-field tender_name --date-field award_date --url-field source_url

python3 -m src.ingest penalty data/penalties.csv \
  --entity-field uniform_number \
  --record-id-field case_id \
  --title-field case --date-field date --url-field source_url

python3 -m src.ingest fraud data/fraud.csv \
  --entity-field uniform_number \
  --record-id-field record_id \
  --title-field title --date-field date --url-field source_url
```

The importer intentionally preserves the raw row and provenance. It does **not** infer that a person or company committed wrongdoing merely because a name appears in a source.

## Official source constraints

- The Ministry of Economic Affairs company open data provides company identifiers and core registration fields. urlOfficial company data documentationhttps://data.gcis.nat.gov.tw/od/rule
- The Judicial Yuan provides a court-decision API, but access requires a Judicial Yuan open-data account/token. Its current specification says records can later be changed or removed, so ingestion must support replacement/removal. citeturn0search36
- Government penalty data is distributed across agencies. For example, the Environmental Ministry publishes enforcement records with actor, date, case, legal basis, fine, appeal and improvement fields; the Financial Supervisory Commission also publishes penalty datasets. citeturn0search0turn0search2
- Fraud-warning data should be treated as a source-backed signal rather than a legal finding.

## Investor-demo MVP

**輸入統編 → 建立企業網絡 → 找到關鍵人物／關聯企業／標案 → 追溯 Evidence → 進行跨來源調查**

The browser workspace includes target-company information, network KPIs, interactive graph layouts, entity filters, pan/zoom, node inspection, and investigation signals.

## Architecture

```text
                   Entity
                     |
          +----------+----------+
          |          |          |
       Company     Person    Organization
          |
          +-----------------------------+
          |              |               |
       Registry       Evidence       Relationships
          |              |               |
          |       +------+------+--------+------+
          |       |      |      |               |
          |    Court   Tender Penalty        Fraud
          |       |      |      |               |
          +-------+------+------+---------------+
                         |
                  Evidence Graph
                         |
                  Investigation UI
```

## Repository layout

```text
src/
  company.py       Official company basic-data client
  db.py            SQLite connection + evidence schema migration
  models.py        Entity graph data models
  evidence.py      Unified evidence model and deterministic IDs
  source_registry.py  Canonical source metadata
  repository.py    Entity, tender, and evidence queries
  ingest.py        CSV/JSON evidence ingestion pipeline
  graph.py         Explainable graph construction + evidence links
  main.py          CLI entry point
  server.py        Local web API + UI server
web/
  index.html       Dependency-free investigation workspace
data/
  README.md        Local data instructions
tests/
  test_models.py   Graph model smoke test
```

## Local data

Large source datasets and databases are intentionally **not committed to Git**. Put them under `data/` locally.

Expected development files:

- `directors.csv`
- `person_index.json`
- `entity.db`
- `tenders_gpa.json`
- future judicial / penalty / fraud source files

## Run locally

Python 3.9+ is supported and the MVP uses the Python standard library.

```bash
python3 -m unittest discover -s tests
python3 -m src.main
python3 -m src.server
```

Then open `http://127.0.0.1:8000` and enter a company uniform number.

## Product direction

1. Finish source-specific adapters for Judicial Yuan court records, procurement, agency penalties and fraud-warning datasets
2. Add entity-resolution candidates and reviewable match evidence
3. Add bounded multi-hop investigation and shortest-path analysis
4. Add effective-date timelines and source update/removal handling
5. Add saved investigations and evidence-backed reports
6. Add explainable AI that separates observed facts from inference
7. Add automated source refresh and monitoring

## Responsible interpretation

A public-record relationship does not by itself establish wrongdoing, beneficial ownership, or a personal relationship. T.E.I. must distinguish **observed facts, source evidence, and system-generated inference**, and expose provenance, dates, relationship types, and confidence.
