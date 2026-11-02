"""Event-scoped review decisions; never creates global aliases or DB writes."""
import argparse
import csv
import json
from pathlib import Path
import re

from scripts.audit_public_news_people import plain_text, verify_inputs, write_csv

ALIASES = {
    "鄭天財 Sra‧Kacaw": ("鄭天財Sra Kacaw", "平地原住民選舉區"),
    "伍麗華 Saidhai．Tahovecahe": ("伍麗華Saidhai‧Tahovecahe", "山地原住民選舉區"),
}


def full_name_tokens(value):
    # Preserve every Chinese and Latin letter, including case. Never strip the
    # Indigenous name or match a Chinese prefix alone.
    return re.sub(r"[\s‧．·]", "", value)


def review(row, roster, members, official_text):
    name = row["姓名"]
    if name in ALIASES:
        canonical, district = ALIASES[name]
        if (row["事件日期"] != "2024-01-13" or str(row["屆別"]) != "11"
                or row["選區或機關"] != district
                or full_name_tokens(name) != full_name_tokens(canonical)):
            raise ValueError("Election event scope changed")
        candidates = [p for p in roster if p["name"] == canonical
                      and p["entity_type"] == "Politician"
                      and any(t["term"] == 11 and t["constituency"] == district for t in p["terms"])]
        official = [p for p in members if p["name"] == canonical
                    and str(p["term"]) == "11" and p["areaName"] == district]
        if len(candidates) != 1 or len(official) != 1:
            raise ValueError("Non-unique official identity")
        return "核准事件限定配對", candidates[0]["entity_id"], "ly-members-11.json"
    if name == "李妍慧":
        if (row["事件日期"] != "2025-08-27" or row["選區或機關"] != "僑務委員會"
                or row["政黨或職務"] != "副委員長"):
            raise ValueError("Historical office scope changed")
        if not all(s in official_text for s in (
                "李姸慧出席緬甸歸僑協會新春團拜", "僑務委員會副委員長李妍慧")):
            raise ValueError("Official same-event alias evidence missing")
        candidates = [p for p in roster if p["name"] == "李姸慧"
                      and p["entity_type"] == "GovernmentOfficial"
                      and any(o["agency"] == "僑務委員會" for o in p["official_observations"])]
        if len(candidates) != 1:
            raise ValueError("Non-unique office identity")
        return "核准事件限定配對；不合併任期", candidates[0]["entity_id"], "ocac-name-variant.html"
    if name == "游錫堃":
        return "保留歷史草稿；永久編號與ID14不同，不核准發布", "", "ly-official-identifiers.pdf"
    return "官方事件已核對；母體外職務，不核准既有實體配對", "", "ey-cabinet-2025.html"


def run(folder):
    sources = verify_inputs(folder)
    roster = json.loads((folder / "development-roster.json").read_text())
    members = json.loads((folder / "ly-members-11.json").read_text())["dataList"]
    official = plain_text((folder / "ocac-name-variant.html").read_text())
    with (folder / "新聞待覆核清單.csv").open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 14:
        raise ValueError("Exception cohort changed")
    for row in rows:
        decision, entity_id, filename = review(row, roster, members, official)
        source = sources[filename]
        row.update({"覆核結果": decision, "核准實體編號": entity_id,
                    "官方覆核來源": source["source_url"], "官方原件雜湊": source["sha256"],
                    "官方取得時間": source["retrieved_at"],
                    "配對範圍": "僅此新聞URL、事件日期、屆別／機關與角色；非全域別名",
                    "發布狀態": "覆核登錄；本表不寫入資料庫、不建立共現關係"})
    if sum(bool(r["核准實體編號"]) for r in rows) != 3:
        raise ValueError("Approved cohort changed")
    write_csv(folder / "十四筆覆核處置.csv", rows)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_directory", type=Path)
    directory = parser.parse_args().snapshot_directory.resolve()
    root = Path(__file__).resolve().parents[1]
    if directory.is_relative_to(root) or directory.stat().st_mode & 0o077:
        parser.error("Use a private snapshot directory outside Git")
    result = run(directory)
    print(f"Reviewed {len(result)}; approved scoped matches 3; DB writes 0")
