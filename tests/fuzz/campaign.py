"""Bounded, reproducible offline fuzzing; denies outbound I/O and keeps repros.

Run: python tests/fuzz/campaign.py --seed 20261118 --cases 5000 --output /tmp/tei-fuzz.json
A PASS is a bounded campaign result, never proof that all inputs are safe.
"""

import argparse
from copy import deepcopy
from contextlib import ExitStack
from io import BytesIO, StringIO
import json
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import random
import sys
import time
from unittest.mock import patch
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import app as entrypoint  # noqa: E402
from src.entities.repository import EntityRepository  # noqa: E402
from src.reports import render_report_html  # noqa: E402
from src.report_pdf import render_report_pdf  # noqa: E402
from src.sources.procurement import lookup_awards, lookup_notice_detail  # noqa: E402
from pypdf import PdfReader  # noqa: E402

SEEDS = [
    "中華電信",
    "公司／組織 & person",
    "<img src=x onerror=alert(1)>",
    "𠮷野😀",
    "\x00",
    "\n",
    "\u202e",
    "ＡＢ１２",
    "A" * 101,
    "",
    "0630800011",
]
IDS = [f"11111111-1111-4111-8111-{i:012d}" for i in range(14)]


def mutation(rng, text):
    text = str(text)
    op = rng.randrange(5)
    if op == 0:
        return text[: rng.randrange(len(text) + 1)]
    if op == 1:
        return text + rng.choice(SEEDS)
    if op == 2:
        at = rng.randrange(len(text) + 1)
        return (
            text[:at]
            + rng.choice(["%", "&", "/", "?", "\x7f", "\t", "中", "😀"])
            + text[at:]
        )
    if op == 3:
        return text * rng.randrange(1, 5)
    return text


class Repo:
    def search(self, *args, **kwargs):
        return {"items": [], "has_more": False}

    def entity(self, *args, **kwargs):
        return None

    def evidence(self, *args, **kwargs):
        return None

    def relationship(self, *args, **kwargs):
        return None

    def graph_neighbors(self, *args, **kwargs):
        return None

    def politician_profile(self, *args, **kwargs):
        return None

    def political_contributions(self, *args, **kwargs):
        return None

    def company_path_at_depth(self, *args, **kwargs):
        return None

    def relationship_path(self, *args, **kwargs):
        return None

    def company_relationship_path(self, *args, **kwargs):
        return None


def api_property(case):
    captured = []
    env = {
        "REQUEST_METHOD": case["method"],
        "PATH_INFO": case["path"],
        "QUERY_STRING": urlencode(case["query"]),
        "REMOTE_ADDR": "127.0.0.1",
        "wsgi.input": BytesIO(case.get("body", "").encode()),
        "CONTENT_LENGTH": str(len(case.get("body", "").encode())),
    }
    body = b"".join(
        entrypoint.app(
            env,
            lambda status, headers: captured.append((int(status.split()[0]), headers)),
        )
    )
    assert captured and (
        captured[0][0] < 500
        or (case["path"] == "/api/procurement-detail" and captured[0][0] == 503)
    ), f"Unexpected HTTP {captured[0][0] if captured else 'missing'}"
    assert (
        int(dict(captured[0][1])["Content-Length"]) == len(body)
        or case["method"] == "HEAD"
    )
    if case["method"] != "HEAD":
        json.loads(body)
    assert b"FUZZ_SECRET_SENTINEL" not in body


def make_api(rng, index):
    text = mutation(rng, rng.choice(SEEDS))
    routes = [
        (
            "/api/v1/search",
            {
                "q": text,
                "limit": rng.choice(
                    ["0", "1", "20", "21", "-1", "NaN", "1.0", "01", "9999999"]
                ),
                "entity_type": rng.choice(
                    ["", "Company", "Person", "CivilOrganization", "Penalty", text]
                ),
            },
        ),
        ("/api/v1/graph/" + rng.choice([IDS[0], text]), {"limit": text, "after": text}),
        (
            "/api/v1/paths",
            {"source": rng.choice([IDS[0], text]), "target": IDS[1], "max_depth": text},
        ),
        (
            "/api/procurement-detail",
            {"unit_id": text, "job_number": text, "filename": text},
        ),
        ("/api/company/" + text, {}),
        ("/api/v1/workspaces", {}),
        (
            "/api/v1/reports/workspace/" + rng.choice([IDS[0], text]),
            {"format": rng.choice(["json", "pdf", text])},
        ),
        ("/api/v1/evidence/" + text, {}),
        ("/api/not-found/" + text, {}),
    ]
    path, query = routes[index % len(routes)]
    return {
        "path": path,
        "query": query,
        "method": rng.choice(["GET", "HEAD", "POST", "PATCH", "DELETE"]),
        "body": rng.choice(
            ["{}", "[]", "null", '"text"', "{bad", json.dumps({"title": text})]
        ),
    }


def award_row():
    prefix = "決標品項:第1品項:得標廠商1:"
    return {
        "date": "20261118",
        "filename": "BDM-1",
        "unit_id": "3.1",
        "job_number": "0630800011",
        "brief": {
            "type": "決標公告",
            "title": "保留有效決標",
            "companies": {
                "names": ["有效廠商"],
                "id_key": {"22659295": [prefix + "廠商代碼"]},
                "name_key": {"有效廠商": [prefix + "廠商名稱"]},
            },
        },
    }


def procurement_property(case):
    before = deepcopy(case)
    with patch("src.sources.procurement._json_get", return_value=case):
        result = lookup_awards("22659295", timeout=1)
    assert result["records"] and result["records"][0]["job_number"] == "0630800011", (
        "One malformed notice erased the valid award"
    )
    assert before == case, "Source payload was mutated"


def make_procurement(rng, index):
    good = award_row()
    invalids = [
        None,
        [],
        1,
        "",
        {"brief": []},
        {"brief": {"type": "決標公告", "companies": []}},
        {"brief": {"type": "決標公告", "companies": {"name_key": [], "id_key": []}}},
        {
            "date": "20261119",
            "filename": "BAD",
            "unit_id": "3.2",
            "job_number": "bad",
            "brief": {
                "type": "決標公告",
                "companies": {
                    "id_key": {"22659295": 42},
                    "name_key": {"壞資料": ["path"]},
                },
            },
        },
    ]
    bad = deepcopy(invalids[index % len(invalids)])
    if isinstance(bad, dict):
        bad[rng.choice(["unit_name", "description", "unused"])] = rng.choice(SEEDS)
    rows = [good, bad]
    rng.shuffle(rows)
    return {"records": rows, "total_records": 2}


def detail_property(case):
    with patch("src.sources.procurement._json_get", return_value={"records": [case]}):
        result = lookup_notice_detail("3.1", "0630800011", "BDM-1", timeout=1)
    assert result["status"] == "ok", (
        "An invalid optional link discarded a valid exact-version notice"
    )
    if result["status"] == "ok":
        for section in ("summary", "bidders", "items", "lifecycle"):
            assert isinstance(result[section], list)


def make_detail(rng, index):
    return {
        "unit_id": "3.1",
        "job_number": "0630800011",
        "filename": "BDM-1",
        "detail": {
            "url": rng.choice(
                [
                    "https://web.pcc.gov.tw/notice",
                    "https://[",
                    "https://evil.invalid/",
                    {"x": 1},
                ]
            ),
            rng.choice(
                [
                    "已公告資料:預算金額",
                    "決標資料:總決標金額",
                    "投標廠商:投標廠商1:廠商名稱",
                ]
            ): rng.choice(SEEDS),
        },
    }


def path_property(case):
    nodes = {
        id: {
            "id": id,
            "entity_type": "Company" if i < 2 else "GovernmentAgency",
            "display_name": str(i),
        }
        for i, id in enumerate(IDS[: case["n"]])
    }
    edges = [
        {
            "id": f"edge-{i}",
            "source": IDS[a],
            "target": IDS[b],
            "source_entity_id": IDS[a],
            "target_entity_id": IDS[b],
            "relationship_type": "MEMBER_OF",
            "primary_evidence": {"id": f"proof-{i}"},
        }
        for i, (a, b) in enumerate(case["edges"])
    ]

    def neighbors(id, **kwargs):
        selected = [e for e in edges if id in (e["source"], e["target"])]
        include = {id} | {x for e in selected for x in (e["source"], e["target"])}
        return {
            "nodes": [nodes[x] for x in include],
            "edges": selected,
            "has_more": False,
        }

    def transport(table, params):
        assert table == "relationships"
        return edges

    repo = EntityRepository(transport=transport)
    repo.graph_neighbors = neighbors

    # Independent exact-length DFS oracle; no relation count exceeds public bounds.
    def walk(node, route, depth):
        if depth == 0:
            return node == IDS[1]
        if node == IDS[1]:
            return False
        return any(
            walk(other, route | {other}, depth - 1)
            for edge in edges
            if node in (edge["source"], edge["target"])
            for other in [edge["target"] if edge["source"] == node else edge["source"]]
            if other not in route
        )

    for depth in (1, 2, 3):
        result = repo.company_path_at_depth(IDS[0], IDS[1], depth=depth)
        assert result["found"] == walk(IDS[0], {IDS[0]}, depth), (
            "Exact intermediary path disagrees with independent oracle"
        )
        if result["found"]:
            route = [result["segments"][0]["from_entity"]["id"]] + [
                s["to_entity"]["id"] for s in result["segments"]
            ]
            assert len(route) == depth + 1 and len(route) == len(set(route))
            assert all(s["evidence"]["id"] for s in result["segments"])


def make_path(rng, index):
    n = rng.randrange(3, 14)
    return {
        "n": n,
        "edges": [
            (a, b) for a in range(n) for b in range(a + 1, n) if rng.random() < 0.2
        ],
    }


def pdf_property(case):
    before = deepcopy(case)
    binary = render_report_pdf(case)
    assert binary.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(binary))
    assert all(p.mediabox.width > p.mediabox.height for p in reader.pages)
    assert before == case, "PDF rendering mutated evidence"
    for page in reader.pages:
        for ann in page.get("/Annots", []):
            action = ann.get_object().get("/A", {})
            if action.get("/S") == "/URI":
                assert str(action.get("/URI", "")).startswith(("https://", "http://"))
    text = "".join("".join((p.extract_text() or "").split()) for p in reader.pages)
    assert case["sentinel"] in text, "PDF lost the generated source marker"


def html_property(case):
    text = render_report_html(case)

    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            assert tag not in ("script", "iframe", "img"), (
                "Source content became active HTML"
            )
            for key, value in attrs:
                assert not key.lower().startswith("on"), (
                    "Source content injected an event handler"
                )
                if key == "href":
                    assert value.startswith(("https://", "http://"))

    Links().feed(text)
    assert case["sentinel"] in text


def make_pdf(rng, index):
    token = f"FUZZCASE{index:05d}"
    label = mutation(
        rng,
        rng.choice(
            [
                "中文公司與來源",
                "LongCompanyAndSource" * 30,
                "<script>alert(1)</script>",
                "混合English123",
            ]
        ),
    )
    return {
        "title": "模糊測試／Fuzz report",
        "methodology": "隔離合成測試資料，不匯入資料庫",
        "report_type": "ENTITY",
        "generated_at": rng.choice(
            ["2026-11-18T14:00:00Z", "115/11/18", "2026", "not-a-date"]
        ),
        "sentinel": token,
        "entity_profiles": [{"display_name": label, "entity_type": "Company"}],
        "sources": [
            {
                "title": token,
                "source_name": "測試來源",
                "source_url": rng.choice(
                    [
                        "https://example.gov.tw/" + ("abc" * rng.randrange(1, 180)),
                        "javascript:alert(1)",
                        "https://[",
                    ]
                ),
                "retrieved_at": "2026-11-18T14:00:00Z",
                "source_record_id": token,
                "source_locator": {"future_field": label},
            }
        ],
        "relationship_graph": {"nodes": [], "edges": []},
    }


TARGETS = {
    "api": (make_api, api_property),
    "procurement": (make_procurement, procurement_property),
    "notice_detail": (make_detail, detail_property),
    "exact_path": (make_path, path_property),
    "pdf": (make_pdf, pdf_property),
    "report_html": (make_pdf, html_property),
}


def shrink(case, property_check):
    """Delta-debug a failing JSON input; retain only reductions still failing."""

    def fails(value):
        try:
            property_check(value)
            return False
        except Exception:
            return True

    current = deepcopy(case)
    if not isinstance(current, dict):
        return current
    for key in list(current):
        if key not in ("records", "detail"):
            continue
        value = current[key]
        if isinstance(value, list):
            for i in range(len(value) - 1, -1, -1):
                attempt = {**current, key: current[key][:i] + current[key][i + 1 :]}
                # Keep a valid sentinel record so shrinking cannot invent the failure.
                if key == "records" and not any(
                    isinstance(x, dict) and x.get("job_number") == "0630800011"
                    for x in attempt[key]
                ):
                    continue
                if fails(attempt):
                    current = attempt
        elif isinstance(value, dict):
            for field in list(value):
                attempt = deepcopy(current)
                del attempt[key][field]
                if fails(attempt):
                    current = attempt
    return current


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20261118)
    parser.add_argument("--cases", type=int, default=5000)
    parser.add_argument("--output", default="/tmp/tei-fuzz.json")
    parser.add_argument("--target", choices=TARGETS)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    report = {
        "seed": args.seed,
        "cases_per_target": args.cases,
        "targets": {},
        "network": "denied",
        "failures": [],
    }
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "urllib.request.urlopen",
                side_effect=AssertionError(
                    "Outbound network forbidden in fuzz campaign"
                ),
            )
        )
        stack.enter_context(patch("app.log_event"))
        stack.enter_context(
            patch("src.sources.procurement._json_get", return_value={"records": []})
        )
        stack.enter_context(patch("app.request_allowed", return_value=True))
        stack.enter_context(
            patch("src.entities.api.EntityRepository", return_value=Repo())
        )
        stack.enter_context(
            patch("app.core.build_company", return_value={"status": "not_found"})
        )
        stack.enter_context(patch("sys.stderr", new=StringIO()))
        for name, (generate, check) in TARGETS.items():
            if args.target and name != args.target:
                continue
            started = time.monotonic()
            failures = {}
            unique = set()
            total = min(args.cases, 100) if name == "pdf" else args.cases
            for index in range(total):
                case = generate(rng, index)
                unique.add(
                    sha256(
                        json.dumps(case, sort_keys=True, ensure_ascii=False).encode()
                    ).hexdigest()
                )
                try:
                    check(case)
                except Exception as exc:
                    fingerprint = type(exc).__name__ + ":" + str(exc)[:180]
                    if fingerprint not in failures:
                        failures[fingerprint] = {
                            "target": name,
                            "seed": args.seed,
                            "index": index,
                            "error": fingerprint,
                            "input": shrink(case, check),
                        }
                    failures[fingerprint]["occurrences"] = (
                        failures[fingerprint].get("occurrences", 0) + 1
                    )
            report["targets"][name] = {
                "cases": total,
                "unique_inputs": len(unique),
                "failure_classes": len(failures),
                "seconds": round(time.monotonic() - started, 3),
            }
            report["failures"].extend(failures.values())
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "failures"}, ensure_ascii=False
        )
    )
    print("Failure classes:", len(report["failures"]))
    return bool(report["failures"])


if __name__ == "__main__":
    raise SystemExit(main())
