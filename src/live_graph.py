"""Live fallback graph built from Taiwan Ministry of Economic Affairs open APIs."""
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List
from .models import EntityGraph, GraphEdge, GraphNode

BASE = "https://data.gcis.nat.gov.tw/od/data/api"
COMPANY_API = BASE + "/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
DIRECTOR_API = BASE + "/4E5F7653-1B91-4DDC-99D5-468530FAE396"
RESPONSIBLE_API = BASE + "/4B61A0F1-458C-43F9-93F3-9FD6DA5E1B08"


def _get_json(url: str, timeout: int = 8) -> List[Dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "TaiwanEntityIntelligence/0.2"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, list) else []


def _query(api: str, field: str, value: str, top: int = 100) -> List[Dict[str, Any]]:
    params = {"$format": "json", "$filter": "{} eq {}".format(field, value), "$skip": "0", "$top": str(top)}
    return _get_json(api + "?" + urllib.parse.urlencode(params))


def live_company_people(uniform_number: str) -> List[Dict[str, Any]]:
    rows = _query(DIRECTOR_API, "Business_Accounting_NO", uniform_number, 100)
    result = []
    for row in rows:
        name = row.get("Person_Name") or row.get("person_name")
        if not name:
            continue
        result.append({
            "uniform_number": uniform_number,
            "company_name": row.get("Juristic_Person_Name") or row.get("company_name") or uniform_number,
            "position": row.get("Person_Position_Name") or row.get("position"),
            "person_name": name,
            "representative": row.get("Representative") or row.get("representative"),
            "shares": row.get("Person_Shareholding") or row.get("shares"),
        })
    return result


def _person_companies(name: str) -> List[Dict[str, Any]]:
    rows = _query(RESPONSIBLE_API, "Responsible_Name", name, 50)
    return [{
        "uniform_number": row.get("Business_Accounting_NO"),
        "company_name": row.get("Company_Name"),
        "position": "負責人",
        "person_name": name,
    } for row in rows if row.get("Business_Accounting_NO") and row.get("Company_Name")]


def live_company_graph(uniform_number: str) -> Dict[str, Any]:
    """Return a bounded graph using only live government open data."""
    basic_rows = _query(COMPANY_API, "Business_Accounting_NO", uniform_number, 1)
    people = live_company_people(uniform_number)
    company_name = ((basic_rows[0] if basic_rows else {}).get("Company_Name")
                    or (people[0]["company_name"] if people else uniform_number))

    graph = EntityGraph()
    company_id = "company:{}".format(uniform_number)
    graph.add_node(GraphNode(id=company_id, type="company", label=company_name,
                             properties={"uniform_number": uniform_number,
                                         "source": "經濟部商工行政資料開放平台"}))

    people = people[:12]
    unique_names = list(dict.fromkeys(p["person_name"] for p in people if p.get("person_name")))
    related: Dict[str, List[Dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_person_companies, name): name for name in unique_names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                related[name] = future.result()
            except Exception:
                related[name] = []

    seen_companies = {uniform_number}
    for person in people:
        name = person.get("person_name")
        if not name:
            continue
        person_id = "person:{}".format(name)
        graph.add_node(GraphNode(id=person_id, type="person", label=name, properties={
            "position": person.get("position"), "shares": person.get("shares"),
            "source": "經濟部公司登記董監事資料"}))
        graph.add_edge(GraphEdge(source=company_id, target=person_id,
                                 relationship=person.get("position") or "董事／監察人關係",
                                 properties={"source": "company_directors", "live": True}))

        for other in related.get(name, [])[:8]:
            other_id = other.get("uniform_number")
            other_name = other.get("company_name")
            if not other_id or not other_name or other_id in seen_companies:
                continue
            seen_companies.add(other_id)
            other_node_id = "company:{}".format(other_id)
            graph.add_node(GraphNode(id=other_node_id, type="company", label=other_name,
                                     properties={"uniform_number": other_id,
                                                 "source": "經濟部公司負責人資料查詢"}))
            graph.add_edge(GraphEdge(source=person_id, target=other_node_id,
                                     relationship="負責人關係",
                                     properties={"source": "company_responsible_person", "live": True}))

    result = graph.to_dict()
    result["data_mode"] = "live_government_open_data"
    result["data_sources"] = [
        {"name": "公司登記基本資料", "url": COMPANY_API},
        {"name": "公司登記董監事資料", "url": DIRECTOR_API},
        {"name": "公司負責人資料查詢", "url": RESPONSIBLE_API},
    ]
    return result
