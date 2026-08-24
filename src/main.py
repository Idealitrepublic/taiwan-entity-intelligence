"""CLI entry point for the Taiwan Entity Intelligence MVP."""

import json
import os
import sys

from .db import connect
from .graph import company_graph
from .repository import company_people


def main() -> int:
    uniform_number = input("請輸入公司統一編號： ").strip()
    if not uniform_number.isdigit():
        print("請輸入純數字的統一編號。")
        return 2

    try:
        conn = connect()
    except FileNotFoundError as exc:
        print(exc)
        return 1

    people = company_people(conn, uniform_number)
    if not people:
        print("找不到此統編的董監事資料。請確認 data/entity.db 已放入最新資料。")
        conn.close()
        return 0

    company_name = people[0]["company_name"]
    print("\n=== {} ({}) ===".format(company_name, uniform_number))
    print("董監事：{} 人".format(len(people)))
    for person in people:
        print(
            "- {} | {}".format(
                person.get("person_name", ""),
                person.get("position", ""),
            )
        )

    graph = company_graph(conn, uniform_number)
    conn.close()

    os.makedirs("outputs", exist_ok=True)
    output = os.path.join("outputs", "company_{}.json".format(uniform_number))
    with open(output, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    print("\n關係圖資料：{} nodes / {} edges".format(
        len(graph["nodes"]), len(graph["edges"])
    ))
    print("已輸出：{}".format(output))
    print("\n下一階段可將這份 graph JSON 接到瀏覽器互動式視覺化。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
