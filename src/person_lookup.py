import csv
import os

DIRECTORS_FILE = "data/directors.csv"


def find_person_companies(person_name):
    print()
    print("=" * 60)
    print("TAIWAN ENTITY INTELLIGENCE")
    print("第二層 B：人物 → 公司")
    print("=" * 60)

    if not os.path.exists(DIRECTORS_FILE):
        print()
        print("找不到資料檔：", DIRECTORS_FILE)
        return

    person_name = person_name.strip()

    print()
    print("正在反查人物資料...")
    print("姓名：", person_name)

    results = []
    seen = set()

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
                    name = row.get("姓名", "").strip()

                    if name != person_name:
                        continue

                    company_id = row.get("統一編號", "").strip()
                    company_name = row.get("公司名稱", "").strip()

                    key = (company_id, company_name)

                    if key in seen:
                        continue

                    seen.add(key)

                    results.append({
                        "company_id": company_id,
                        "company_name": company_name,
                        "position": row.get("職稱", "").strip(),
                        "representative": row.get("所代表法人", "").strip(),
                        "shares": row.get("持有股份數", "").strip()
                    })

            break

        except UnicodeDecodeError:
            results = []
            seen = set()
            continue

    if not results:
        print()
        print("找不到此人物的公司關係。")
        return

    print()
    print("=" * 60)
    print("PERSON → COMPANIES")
    print("=" * 60)

    for index, company in enumerate(results, 1):

        print()
        print("[{}] {}".format(
            index,
            company["company_name"]
        ))

        print("    統編：", company["company_id"])
        print("    職稱：", company["position"])

        if company["representative"]:
            print(
                "    所代表法人：",
                company["representative"]
            )

        if company["shares"]:
            print(
                "    持有股份數：",
                company["shares"]
            )

    print()
    print("=" * 60)
    print("找到公司數量：", len(results))
    print("=" * 60)


if __name__ == "__main__":

    person_name = input("請輸入人物姓名：").strip()

    if person_name:
        find_person_companies(person_name)
    else:
        print("請輸入人物姓名。")
