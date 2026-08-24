import sqlite3

DB = "data/entity.db"

db = sqlite3.connect(DB)

name = input("請輸入人物姓名： ").strip()

rows = db.execute("""
SELECT DISTINCT
    統一編號,
    公司名稱,
    職稱,
    所代表法人,
    持有股份數
FROM company_directors
WHERE 姓名 = ?
ORDER BY 公司名稱
""", (name,)).fetchall()

print()
print("=" * 60)
print("人物：", name)
print("關聯公司：", len(rows))
print("=" * 60)

for i, row in enumerate(rows, 1):
    company_id, company_name, position, representative, shares = row

    print()
    print("[{}] {}".format(i, company_name))
    print("    統編：", company_id)
    print("    職稱：", position)

    if representative:
        print("    所代表法人：", representative)

    if shares:
        print("    持有股份數：", shares)

db.close()
