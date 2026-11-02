"""Offline inventory of public-duty news against explicit official snapshots.

Never fetches, ingests, publishes, resolves an identity, or connects to a DB.
Inputs/output must live outside Git. A corroborated observation is not a graph
edge, a statement about present office, or a finding of wrongdoing.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LEGISLATOR_NAMESPACE = "tw:legislative_yuan:legislator_number"
CITIES = ("台北市 新北市 桃園市 台中市 台南市 高雄市 基隆市 新竹市 新竹縣 苗栗縣 "
          "彰化縣 南投縣 雲林縣 嘉義市 嘉義縣 屏東縣 宜蘭縣 花蓮縣 台東縣 澎湖縣 金門縣 連江縣").split()
PARTIES = {"民進黨": "民主進步黨", "國民黨": "中國國民黨", "民眾黨": "台灣民眾黨"}
CABINET_ROLES = {
    "行政院祕書長": ("行政院", "秘書長"), "行政院副秘書長": ("行政院", "副秘書長"),
    "經濟部長": ("經濟部", "部長"), "運動部長": ("運動部", "部長"),
    "運動部次長": ("運動部", "政務次長"), "運動部常次": ("運動部", "常務次長"),
    "數發部長": ("數位發展部", "部長"), "數發部次長": ("數位發展部", "次長"),
    "衛福部長": ("衛生福利部", "部長"), "衛福部次長": ("衛生福利部", "常務次長"),
    "教育部次長": ("教育部", "政務次長"), "環境部次長": ("環境部", "政務次長"),
    "國發會主委": ("國家發展委員會", "主任委員"),
    "原住民族委員會副主委": ("原住民族委員會", "副主任委員"),
    "僑委會副委員長": ("僑務委員會", "副委員長"),
}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.stack = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in {"br", "img", "meta", "hr", "link", "input"}:
            self.stack.append(tag)
        if tag in {"p", "br", "h2", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "h2", "li"}:
            self.parts.append("\n")
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]

    def handle_data(self, value):
        if not {"script", "style"}.intersection(self.stack):
            self.parts.append(value)


def plain_text(raw):
    parser = PlainText()
    parser.feed(raw)
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def article(raw):
    # Parse only the body; names in navigation, related articles or scripts are
    # not evidence of an event in the selected article.
    marker = 'class="paragraph"'
    if marker not in raw:
        raise ValueError("Article body not found; manual source review required")
    return plain_text(raw[raw.index(marker):])


def regional_events(raw):
    events, city = [], None
    for line in article(raw).split("（編輯：", 1)[0].splitlines():
        if line in CITIES:
            city = line
        elif re.fullmatch(r"第\d+選區：.+", line):
            if city is None:
                raise ValueError("District without municipality")
            district, name = line.split("：", 1)
            events.append({"name": name, "constituency": city.replace("台", "臺") +
                           district.replace("選區", "選舉區")})
        elif any(line.startswith(item + "：") for item in CITIES):
            city, name = line.split("：", 1)
            events.append({"name": name, "constituency": city.replace("台", "臺") + "選舉區"})
        elif line.startswith(("平地原住民立法委員：", "山地原住民立法委員：")):
            district, names = line.split("：", 1)
            events.extend({"name": name, "constituency": district.replace("立法委員", "選舉區")}
                          for name in names.split("、"))
    if len(events) != 79:
        raise ValueError("Regional source changed; expected 79 election observations")
    return [dict(row, term=11, date="2024-01-13", event="選舉結果報導") for row in events]


def party_events(raw):
    lines = article(raw).split("（編輯：", 1)[0].splitlines()
    events = []
    for label, party in PARTIES.items():
        index = lines.index(label)
        paragraph = lines[index + 1]
        # The first party paragraph describes a reserved seat separately.
        names = paragraph.split("，", 1)[0].rstrip("。").split("、")
        if label == "民進黨":
            reserved = re.search(r"排名第15的([^，]+)", paragraph)
            if not reserved:
                raise ValueError("Reserved-seat observation missing")
            names.append(reserved.group(1))
        if len(names) != (8 if label == "民眾黨" else 13):
            raise ValueError("Party source changed; review before continuing")
        events.extend({"name": name.strip(), "party": party, "term": 11,
                       "constituency": "全國不分區及僑居國外國民", "date": "2024-01-13",
                       "event": "選舉結果報導"} for name in names)
    return events


def cabinet_events(raw, official_raw):
    body = article(raw).split("【內閣改組名單】", 1)[1].split("\n#", 1)[0]
    official_paragraphs = [plain_text(part) for part in re.findall(r"<p\b[^>]*>([\s\S]*?)</p>", official_raw)]
    events = []
    for line in body.splitlines():
        if "：" not in line:
            continue
        label, name = line.split("：", 1)
        if label not in CABINET_ROLES or not name:
            raise ValueError("Cabinet news lacks official corroboration")
        agency, role = CABINET_ROLES[label]
        # The official paragraph must name this person and the role. Some
        # shared-subject paragraphs use a predecessor agency (體育署) rather
        # than repeating the new agency; retain the fixed reviewed role map.
        if not any(name in paragraph and role in paragraph for paragraph in official_paragraphs):
            raise ValueError("Official person/role context missing")
        events.append({"name": name, "agency": agency, "role": role,
                       "date": "2025-08-27", "event": "人事異動公告／擬任，非生效日"})
    if len(events) != 16:
        raise ValueError("Cabinet source changed; expected 16 observations")
    return events


def match_event(event, roster, terms):
    """Return contextual candidates only. No aliases or name-only matching."""
    matches = []
    for person in roster:
        if person["name"] != event["name"]:
            continue
        if "term" in event and person["entity_type"] == "Politician":
            for term in terms:
                if (term["entity_id"] == person["entity_id"] and term["term"] == event["term"]
                        and term["constituency"] == event["constituency"]
                        and (not event.get("party") or term["party"] == event["party"])):
                    matches.append(person["entity_id"])
        elif event.get("agency") and event.get("role") and person["entity_type"] == "GovernmentOfficial":
            if any(obs["agency"] == event["agency"] and obs["role"] == event["role"]
                   for obs in person["official_observations"]):
                matches.append(person["entity_id"])
    return sorted(set(matches))


def verify_inputs(folder):
    manifest = json.loads((folder / "acquisition.json").read_text())
    for source in manifest:
        name = source["file"]
        if Path(name).name != name:
            raise ValueError("Unsafe snapshot path")
        data = (folder / name).read_bytes()
        if len(data) != source["bytes"] or hashlib.sha256(data).hexdigest() != source["sha256"]:
            raise ValueError("Snapshot integrity check failed")
    return {row["file"]: row for row in manifest}


def write_csv(path, rows):
    if not rows:
        raise ValueError("Empty inventory output")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def run(folder):
    sources = verify_inputs(folder)
    roster = json.loads((folder / "development-roster.json").read_text())
    terms = json.loads((folder / "development-terms.json").read_text())["political_terms"]
    members = json.loads((folder / "ly-members-11.json").read_text())["dataList"]
    committees = json.loads((folder / "ly-committee-current.json").read_text())["dataList"]
    def read(name):
        return (folder / name).read_text()
    groups = [
        ("cna-regional-2024.html", regional_events(read("cna-regional-2024.html"))),
        ("cna-party-complete-2024.html", party_events(read("cna-party-complete-2024.html"))),
        ("cna-cabinet-2025.html", cabinet_events(read("cna-cabinet-2025.html"), read("ey-cabinet-2025.html"))),
    ]
    results, per_source = [], []
    for filename, events in groups:
        matched = 0
        for event in events:
            ids = match_event(event, roster, terms)
            matched += len(ids) == 1
            results.append({"姓名": event["name"], "事件日期": event["date"], "事件性質": event["event"],
                            "屆別": event.get("term", ""), "選區或機關": event.get("constituency", event.get("agency", "")),
                            "政黨或職務": event.get("party", event.get("role", "")),
                            "結果": "脈絡核對相符，未發布" if len(ids) == 1 else "待人工覆核，禁止自動連線",
                            "候選實體編號": ";".join(ids), "新聞來源": sources[filename]["source_url"],
                            "原件雜湊": sources[filename]["sha256"], "取得時間": sources[filename]["retrieved_at"]})
        per_source.append({"file": filename, "observations": len(events), "context_matched": matched,
                           "pending": len(events) - matched})
    exact_ids, changed_terms = [], []
    for term in terms:
        person = next(row for row in roster if row["entity_id"] == term["entity_id"])
        current = [row for row in members if row["name"] == person["name"] and
                   str(row["term"]) == str(term["term"]) and row["areaName"] == term["constituency"]]
        actual = {row["lgno"] for row in committees if row["name"] == person["name"] and
                  str(row["term"]) == str(term["term"])}
        if actual == {term["lgno"]}:
            exact_ids.append(term["entity_id"])
        if len(current) != 1 or any((current[0].get(key) or None) !=
                                   (term[field].replace("-", "/") if term[field] else None)
                                   for key, field in [("onboardDate", "start_date"), ("leaveDate", "end_date")]):
            changed_terms.append(term["entity_id"])
    by_number = defaultdict(set)
    for row in committees:
        by_number[row["lgno"]].add(row["name"])
    known = {row["name"] for row in roster if row["entity_type"] == "Politician"}
    missing = [{key: row.get(key) for key in ("name", "term", "areaName", "onboardDate", "leaveDate")}
               for row in members if row["name"] not in known]
    heads_raw = read("ey-heads-current.html")
    cards = re.findall(r'<li class="member_img[^>]*>([\s\S]*?)</li>', heads_raw)
    heads_match = 0
    for person in roster:
        if person["entity_type"] != "GovernmentOfficial":
            continue
        obs = person["official_observations"][0]
        cards_for_person = [card for card in cards if obs["profile_url"] in unescape(card)]
        if len(cards_for_person) == 1:
            content = plain_text(cards_for_person[0])
            heads_match += all(word in content for word in (person["name"], obs["agency"], obs["role"]))
    inventory = []
    for person in roster:
        observations = [row for row in results if person["entity_id"] == row["候選實體編號"]]
        inventory.append({"姓名": person["name"], "類型": "政治人物" if person["entity_type"] == "Politician" else "政府官員",
                          "實體編號": person["entity_id"], "已核對新聞觀察數": len(observations),
                          "盤點狀態": "有本輪脈絡核對；未發布新聞關係" if observations else "未有本輪相符新聞，非無新聞",
                          "官方來源": ";".join(sorted({row["source_url"] for row in person["official_observations"]})),
                          "證據編號": ";".join(row["evidence_id"] for row in person["official_observations"]),
                          "任期或職務": json.dumps(person["terms"] or [{"機關": row["agency"], "職務": row["role"]}
                                                              for row in person["official_observations"]], ensure_ascii=False)})
    summary = {"cohort_entities": len(roster), "types": dict(Counter(row["entity_type"] for row in roster)),
               "sources": per_source, "context_matched_entities": sum(row["已核對新聞觀察數"] > 0 for row in inventory),
               "matching_current_term_api_identifier": len(exact_ids), "changed_term_facts": changed_terms,
               "members_not_in_published_cohort": missing, "matching_current_heads": heads_match,
               "api_numbers_reused_for_different_names": sum(len(names) > 1 for names in by_number.values()),
               "published_or_mutated_rows": 0}
    write_csv(folder / "公眾人物盤點.csv", inventory)
    write_csv(folder / "新聞事件身分核對.csv", results)
    write_csv(folder / "新聞待覆核清單.csv", [row for row in results if row["結果"].startswith("待人工")])
    path = folder / "inventory-summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    path.chmod(0o600)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_directory", type=Path)
    args = parser.parse_args()
    folder = args.snapshot_directory.resolve()
    if folder.is_relative_to(ROOT) or not folder.is_dir() or folder.stat().st_mode & 0o077:
        parser.error("Use an owner-only local snapshot directory outside the repository")
    print(json.dumps(run(folder), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
