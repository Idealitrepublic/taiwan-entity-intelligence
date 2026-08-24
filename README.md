# Taiwan Entity Intelligence

Taiwan Entity Intelligence is an investigation-oriented MVP for turning public Taiwanese company, director, and government procurement information into an explorable relationship network.

## Investor-demo MVP

The current product experience is designed around a simple workflow:

**輸入統編 → 建立企業網絡 → 找到關鍵人物／關聯企業／標案 → 點擊節點追查上下文**

The browser workspace now includes:

- Target company profile and official basic-data summary
- Network KPI cards: nodes, relationships, people, related companies, tenders, high-connectivity entities
- Interactive relationship graph with radial, hierarchical, and compact layouts
- Entity-type filters for companies, people, and tenders
- Pan / zoom / reset controls
- Click-to-inspect entity details and direct relationships
- Focus-on-company and full-graph modes
- A compact investigation-signal panel that summarizes observable network structure
- Dependency-free frontend: no frontend framework or CDN is required for the MVP

The interaction model is intentionally inspired by mature graph-investigation products: progressive visual exploration, search/filter controls, multiple layouts, entity detail panels, and relationship-focused inspection. Mature tools such as Linkurious and Maltego provide similar investigation primitives including filtering, neighborhood exploration, multiple layouts, node/edge details, and graph export/collaboration workflows. This repository does **not** copy their proprietary implementation or UI.

## Data returned

Input a Taiwan company uniform number and return:

- Official company basic information from Taiwan's Ministry of Economic Affairs open-data API
- Directors / supervisors and corporate representatives from the local entity database
- Related companies through shared people
- Government tender / winner records when supported by the local tender schema
- A graph JSON representation
- A local browser investigation workspace

The official company-data API is documented by the Ministry of Economic Affairs' commercial administration open-data platform. urlOfficial API documentationhttps://data.gcis.nat.gov.tw/od/rule

## Architecture

```text
Company uniform number
        |
        +--------------------+
        |                    |
        v                    v
Official company API     Local SQLite
        |                    |
        |              +-----+-----+
        |              |           |
        |              v           v
        |           People      Tenders
        |              |           |
        +--------------+-----------+
                       v
                  Entity Graph
                       |
                 +-----+-----+
                 |           |
                 v           v
              JSON       Investigation UI
```

## Repository layout

```text
src/
  company.py       Official company basic-data client
  db.py            SQLite connection/schema helpers
  models.py        Entity graph data models
  repository.py    Company/person/tender queries
  graph.py         Graph construction
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

Expected local files:

- `directors.csv`
- `person_index.json`
- `entity.db`
- `tenders_gpa.json`

The current MVP reads the existing SQLite tables `company_directors`, `tenders`, and `tender_winners` when the relevant columns are available.

## Run locally

Python 3.9+ is supported. The MVP currently uses the Python standard library.

```bash
python3 -m unittest discover -s tests
python3 -m src.main
```

For the browser UI:

```bash
python3 -m src.server
```

Then open `http://127.0.0.1:8000` and enter a company uniform number. `20828393` is a useful local demo target when the corresponding company data exists in your local database. The UI also has a **載入 Demo** button.

## Product direction

The MVP is deliberately moving toward an investigation product rather than a static chart. The next product layers are:

1. Bounded multi-hop expansion so investigators can progressively reveal a neighborhood instead of loading everything at once
2. Full-text / fuzzy entity search across companies and people
3. Source provenance, effective dates, confidence, and evidence for every node/edge
4. Tender analysis by agency, date, amount, and winner
5. Shortest-path and shared-person analysis between two entities
6. Timeline and geo views where the underlying data supports them
7. Saved investigations / cases and exportable reports
8. Explainable AI that summarizes observed relationships without presenting inference as fact
9. Automated data refresh pipelines and production deployment

## Responsible interpretation

A public-record relationship does not by itself establish wrongdoing, beneficial ownership, or a personal relationship. The product should distinguish facts from inference and show source provenance, dates, relationship types, and confidence scores.
