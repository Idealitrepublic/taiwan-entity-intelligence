import csv
import os

DIRECTORS_FILE = "data/directors.csv"


def find_company_people(uniform_number):
    print()
    print("=" * 60)
    print("TAIWAN ENTITY INTELLIGENCE")
    print("第二層：人物 ↔ 公司")
    print("=" * 60)

    if not os.path.exists(DIRECTORS_FILE):
        print("找不到資料檔：", DIRECTORS_FILE)
        return []

    print()
    print("正在搜尋公司董監事資料...")
    print("統一編號：", uniform_number)

    people = []

    encodings = ["utf-8-sig", "utf-8", "cp950"]

    for encoding in encodings:
        try:
            with open(
                DIRECTORS_FILE,
                "r",
                encoding=encoding,
                newline=""
            ) as file:

                reader = csv.DictReader(file)

                for row in reader:
                    company_id = row.get("統一編號", "").strip()

                    if company_id == uniform_number:
                        people.append({
                            "company_id": company_id,
                            "company_name": row.get("公司名稱", "").strip(),
                            "position": row.get("職稱", "").strip(),
                            "name": row.get("姓名", "").strip(),
                            "representative": row.get("所代表法人", "").strip(),
                            "shares": row.get("持有股份數", "").strip()
                        })

            break

        except UnicodeDecodeError:
            people = []
            continue

    if not people:
        print()
        print("找不到這家公司的董監事資料。")
        return []

    company_name = people[0]["company_name"]

    print()
    print("=" * 60)
    print("公司：", company_name)
    print("統編：", uniform_number)
    print("=" * 60)

    print()

    for index, person in enumerate(people, 1):
        print("[{}] {}".format(index, person["name"]))
        print("    職稱：", person["position"])

        if person["representative"]:
            print("    所代表法人：", person["representative"])

        if person["shares"]:
            print("    持有股份數：", person["shares"])

        print("-" * 60)

    print()
    print("董監事數量：", len(people))

    return people


if __name__ == "__main__":
    uniform_number = input("請輸入公司統一編號：").strip()

    if uniform_number.isdigit():
        find_company_people(uniform_number)
    else:
        print("請輸入純數字的統一編號。")
