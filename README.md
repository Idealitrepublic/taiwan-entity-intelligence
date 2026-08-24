# Taiwan Entity Intelligence

Taiwan Entity Intelligence is an MVP for turning public Taiwanese company, director, and government procurement information into a searchable relationship graph.

## MVP goal

Input a Taiwan company uniform number and return:

- Company basic information
- Directors / supervisors and representatives
- Related companies through people and corporate representatives
- Government tender / procurement history when local tender data is available
- A graph-friendly JSON representation for future visualization

## Architecture

```text
Company uniform number
        |
        v
  Company Resolver
        |
   +----+----+----------------+
   |         |                |
   v         v                v
People    Related         Tenders
   |       Companies          |
   +---------+---------------+
             v
        Entity Graph
             |
             v
      Visualization / AI
```

## Repository layout

```text
src/
  company.py          Company data access layer
  people.py           Company -> people queries
  person_lookup.py    Person -> companies queries
  graph_query.py      Graph-oriented query layer

data/
  README.md           Local data instructions

tests/
  (MVP tests)
```

## Data policy

Large source datasets and local databases are intentionally **not committed to Git**. Put local datasets under `data/` on your development machine and document their schema/source here instead.

Expected local files may include:

- `directors.csv`
- `person_index.json`
- `entity.db`
- `tenders_gpa.json`

Do not commit personal credentials, API keys, secrets, or restricted datasets.

## Development

Python 3.9+ is supported for the current MVP.

Create an environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the current query prototype:

```bash
python3 src/graph_query.py
```

## Roadmap

1. Normalize company and person entities
2. Build company <-> person edges
3. Build company <-> tender / winner edges
4. Add multi-hop graph traversal
5. Add graph visualization web UI
6. Add explainable AI relationship analysis
7. Add source provenance and confidence scores
8. Add automated data refresh pipelines

## Important

This project is an intelligence/research tool. A relationship in public records does not by itself establish wrongdoing, beneficial ownership, or a personal relationship. The eventual product should display source provenance, dates, relationship types, and confidence rather than presenting inference as fact.
