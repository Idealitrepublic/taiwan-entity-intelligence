"""CLI entry point for the Taiwan Entity Intelligence MVP."""

import json
import os
import sys

from .company import get_company
from .db import connect
from .graph import company_graph
from .repository import company_people


def main() -> int:
    uniform_number = input("請輸入公司統一編號： ").strip()
    if not uniform_number.isdigit():
        print("請輸入純數字的統一編號。")
        return 2

    basic = None
    try:
        basic = get_company(uniform_number)
    except Exception as exc:
        print("官方公司基本資料查詢失敗：{}".format(exc))

    try:
        conn = connect()
    except FileNotFoundError as exc:
        print(exc)
        return 1

    people = company_people(conn, uniform_number)
    if not people and not basic:
        print("找不到此統編。")
        conn.close()
        return 0

    company_name = (
        (basic or {}).get("Company_Name")
        or (people[0]["company_name"] if people else uniform_number)
    )

    print("\n=== {} ({}) ===".format(company_name, uniform_number))
    if basic:
        print("狀態：{}".format(basic.get("Company_Status_Desc", "")))
        print("代表人：{}".format(basic.get("Responsible_Name", "")))
        print("資本額：{}".format(basic.get("Capital_Stock_Amount", "")))
        print("實收資本額：{}".format(basic.get("Paid_In_Capital_Amount", "")))
        print("地址：{}".format(basic.get("Company_Location", "")))
        print("設立日期：{}".format(basic.get("Company_Setup_Date", "")))

    print("董監事：{} 人".format(len(people)))
    for person in people:
        print("- {} | {}".format(
            person.get("person_name", ""),
            person.get("position", ""),
        ))

    graph = company_graph(conn, uniform_number)
    conn.close()

    os.makedirs("outputs", exist_ok=True)
    output = os.path.join("outputs", "company_{}.json".format(uniform_number))
    with open(output, "w", encoding="utf-8") as f:
        json.dump({"company": basic, "graph": graph}, f, ensure_ascii=False, indent=2)

    print("\n關係圖資料：{} nodes / {} edges".format(
        len(graph["nodes"]), len(graph["edges"])
    ))
    print("已輸出：{}".format(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
