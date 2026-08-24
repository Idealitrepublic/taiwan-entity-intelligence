# Taiwan Entity Intelligence

Taiwan Entity Intelligence is an MVP for turning public Taiwanese company, director, and government procurement information into a searchable relationship graph.

## MVP

Input a Taiwan company uniform number and return:

- Official company basic information from Taiwan's Ministry of Economic Affairs open-data API
- Directors / supervisors and corporate representatives from the local entity database
- Related companies through shared people
- Government tender / winner records when supported by the local tender schema
- A graph JSON representation
- A local browser UI for visual exploration

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
              JSON       Browser UI
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
  index.html       Dependency-free graph viewer
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

Then open `http://127.0.0.1:8000` and enter a company uniform number, for example `20828393` if that company exists in your local database.

## Roadmap

1. Normalize company and person entities
2. Improve tender/winner schema mapping and source provenance
3. Add bounded multi-hop graph traversal
4. Add interactive graph filtering, search, and relationship details
5. Add source/date/confidence for every edge
6. Add explainable AI relationship analysis
7. Add automated data refresh pipelines
8. Add production API/authentication/deployment

## Responsible interpretation

A public-record relationship does not by itself establish wrongdoing, beneficial ownership, or a personal relationship. The product should distinguish facts from inference and show source provenance, dates, relationship types, and confidence scores.
