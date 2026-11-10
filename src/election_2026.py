"""The CEC September 7 registration snapshot for the 2026 local elections."""
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from io import BytesIO
import re
import unicodedata
from zipfile import ZipFile

from .entities.models import stable_id

ROSTER_URL = "https://www.cec.gov.tw/central/article/64709"
ZIP_URL = "https://www.cec.gov.tw/api/file/zip/64709.zip"
SNAPSHOT_DATE = "2026-09-07"
ELECTION_DATE = "2026-11-28"
DATASET = "cec-2026-local-election-registration"
EXPECTED_COUNT = 19695
EXPECTED_BY_OFFICE = (23, 610, 58, 892, 16, 94, 465, 3437, 14100)
EXPECTED_IMAGE_NAMES = 21
COUNTIES = (
    "臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市",
    "基隆市", "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣", "南投縣",
    "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣", "金門縣", "連江縣",
)
SOURCES = (
    ("1-1", "直轄市長", "bb9a8d7a-9b8a-41ec-8e23-33efd009385a", 1),
    ("2-1", "直轄市議員", "ccd7e51a-5fd0-4ea0-a81b-a120cd550c9c", 22),
    ("3-1", "縣市長", "370f3bbf-6408-4fdc-b8d8-9b9214913f74", 2),
    ("4-1", "縣市議員", "9ccb6224-20be-479e-931f-81aa6155f28a", 44),
    ("5-", "直轄市山地原住民區長", "1278f66e-1d15-4ecf-aeeb-9ea5cba61f00", 1),
    ("6-", "直轄市山地原住民區民代表", "f3b665f2-6f0b-485f-a1eb-17d152849317", 3),
    ("7-", "鄉鎮市長", "a7b4f3d3-dad3-4e61-9036-2cd21cf29d92", 12),
    ("8-", "鄉鎮市民代表", "437a9da7-eaa7-47b9-9571-789eeb48ed18", 165),
    ("9-", "村里長", "f1abbda2-229b-4a02-8dfb-58beb3ceca61", 674),
)
HEADERS = ("選舉區", "登記日期", "姓名", "推薦之政黨", "備註")
REG_DATE = re.compile(r"115/(08/31|09/0[1-4])")
PDF_HASHES = (
    "5ab6ec29145feab84f8e697495f039217bb18ace252382e7e150bb1ea7ae18fa",
    "28a9bf7edeb4b2f45a0b3ca473d59c930fcf8cba575c8879fb33397815116090",
    "97c32aa206bfd5d1e07d5b9658f853b6b038053b662dd04fdd0132af614a8136",
    "11d6334e4a5cf3bc7539455ef047ac40f62e250d3c151348683ab1141f83d517",
    "4fc59f8d50a7c1ebe7e3e7e477a5ebce6fc01c3f9718aa604db4b7d036a910a4",
    "bc4495a11991ec3a6ce2acdbcf27fb6e8ff8d12289ed3395775f19e83fd2ce16",
    "108be0fe67ae22ce79b4767df6023f3331f241b5b85e6dc78ebaf4e22e512989",
    "a457e997695384260ae347d9c2ca023426819ca8641bc9f84e080cc151361761",
    "55c957f323766eca89239027352a38f53a17af2aea22e8a0526d1d7484f06a21",
)


def pdf_url(office_index):
    return f"https://www.cec.gov.tw/api/file/{SOURCES[office_index][2]}.pdf"


@dataclass(frozen=True)
class Registration:
    office: int
    page: int
    row: int
    district: str
    name: str | None
    registered_on: str
    recommending_party: str | None

    @property
    def id(self):
        return stable_id("election-registration", DATASET,
                         f"{SNAPSHOT_DATE}:{self.office}:{self.page}:{self.row}")


def parse_page(fragments, office, page):
    """Assign wrapped cell fragments by the table header and nearest date row."""
    headers = {}
    for f in sorted(fragments, key=lambda fragment: -fragment["ty"]):
        if f["text"].strip() in HEADERS:
            headers.setdefault(f["text"].strip(), f)
    if set(headers) != set(HEADERS):
        raise ValueError(f"Unexpected CEC columns in office {office}, page {page}")
    header_y = min(f["ty"] for f in headers.values())
    centers = [(headers[key]["tx"] + headers[key]["displaced_tx"]) / 2 for key in HEADERS]
    bounds = [(left + right) / 2 for left, right in zip(centers, centers[1:])]
    cells = [f for f in fragments if f["ty"] < header_y - 1 and f["text"].strip()]
    dates = sorted((-f["ty"], f["text"].strip()) for f in cells if REG_DATE.fullmatch(f["text"].strip()))
    if not dates or len({y for y, _ in dates}) != len(dates):
        raise ValueError(f"Missing or ambiguous CEC registration dates in office {office}, page {page}")
    y_values = [y for y, _ in dates]
    rows = [[[] for _ in HEADERS] for _ in dates]
    for f in cells:
        y = -f["ty"]
        nearest = bisect_left(y_values, y)
        index = min(range(max(0, nearest - 1), min(nearest + 1, len(rows))),
                    key=lambda i: abs(y_values[i] - y))
        x = (f["tx"] + f["displaced_tx"]) / 2
        column = bisect_left(bounds, x)
        if column != 4:
            rows[index][column].append((y, f["tx"], f["text"].strip()))

    def cell(parts, separator):
        return separator.join(text for _, _, text in sorted(parts))

    for row, ((_, expected_date), (district_parts, date_parts, name_parts, party_parts, _)) in enumerate(
            zip(dates, rows), 1):
        district = cell(district_parts, "").replace(" ", "")
        name = " ".join(cell(name_parts, " ").split())
        party = cell(party_parts, "").replace(" ", "")
        context = f"office {office}, page {page}, row {row}"
        if (cell(date_parts, "") != expected_date or district[:3] not in COUNTIES
                or (name and not 2 <= len(name) <= 100) or not party or len(party) > 50
                or any(re.search(r"[\x00-\x1f\ufffd]", value) for value in (district, name, party))
                or re.search(r"\d{3,}|@|https?:", name + party)):
            raise ValueError(f"Unverified CEC registration cell at {context}")
        month, day = map(int, expected_date.split("/")[1:])
        yield Registration(office, page, row, district, name or None, date(2026, month, day).isoformat(),
                           None if party == "無" else party)


def read_roster(zip_path):
    # pypdf 6.10 is pinned in requirements-dev. BT geometry preserves wrapped
    # districts and romanized names that plain PDF text interleaves across columns.
    from pypdf import PdfReader
    from pypdf._text_extraction._layout_mode import text_show_operations
    from pypdf.generic import ContentStream

    registrations, digests = [], []
    with ZipFile(zip_path) as archive:
        for office, (prefix, label, _, page_count) in enumerate(SOURCES):
            members = [file for file in archive.infolist() if file.filename.startswith(prefix + "(")]
            if len(members) != 1 or members[0].file_size > 12_000_000:
                raise ValueError(f"Missing or oversized CEC document: {label}")
            content = archive.read(members[0])
            digests.append(sha256(content).hexdigest())
            if digests[-1] != PDF_HASHES[office]:
                raise ValueError(f"CEC PDF hash changed: {label}")
            pdf = PdfReader(BytesIO(content), strict=True)
            if len(pdf.pages) != page_count:
                raise ValueError(f"CEC page count changed: {label}")
            for page_number, page in enumerate(pdf.pages, 1):
                operations = ContentStream(page["/Contents"].get_object(), page.pdf, "bytes").operations
                fragments = text_show_operations(iter(operations), page._layout_mode_fonts())
                rows = list(parse_page(fragments, office, page_number))
                if any(row.name is None for row in rows) and not len(page.images):
                    raise ValueError(f"Missing name without an image in office {office}, page {page_number}")
                registrations.extend(rows)
    counts = Counter(r.office for r in registrations)
    if (tuple(counts[i] for i in range(len(SOURCES))) != EXPECTED_BY_OFFICE
            or sum(r.name is None for r in registrations) != EXPECTED_IMAGE_NAMES
            or {r.district[:3] for r in registrations} != set(COUNTIES)):
        raise ValueError(f"CEC coverage check failed: {len(registrations)} parsed registrations")
    return registrations, digests


def search_key(value):
    normalized = unicodedata.normalize("NFKC", value or "").casefold().replace("台", "臺")
    return "".join(normalized.split())


def search_registrations(transport, term, limit, offset):
    """Search the allowlisted registration rows in the published county shards."""
    key = search_key(term)
    params = {"dataset": f"eq.{DATASET}", "select": "raw", "order": "id.asc",
              "limit": len(COUNTIES)}
    if key in COUNTIES:
        params["title"] = f"eq.{key}"
    shards = transport("source_records", params)
    if not shards:
        return None
    matches = []
    for shard in shards:
        raw = shard["raw"]
        if raw.get("snapshot_date") != SNAPSHOT_DATE:
            continue
        for record in raw["rows"]:
            name = search_key(record["name"])
            office = SOURCES[record["office"]][1]
            if key == name:
                rank = 0
            elif name.startswith(key):
                rank = 1
            elif key in name:
                rank = 2
            elif any(key in search_key(value) for value in
                     (record["district"], office, record["recommending_party"])):
                rank = 3
            else:
                continue
            matches.append((rank, record))
    matches.sort(key=lambda item: (item[0], item[1]["office"], item[1]["page"], item[1]["row"]))
    items = []
    for _, row in matches[offset:offset + limit]:
        items.append({
            "name": row["name"], "district": row["district"], "office": SOURCES[row["office"]][1],
            "registered_on": row["registered_on"], "recommending_party": row["recommending_party"],
            "status": "registered_snapshot", "source_page": row["page"], "source_row": row["row"],
            "source_url": pdf_url(row["office"]), "source_sha256": PDF_HASHES[row["office"]],
            "context": row.get("context"),
        })
    return {"items": items, "total": len(matches), "snapshot_date": SNAPSHOT_DATE,
            "election_date": ELECTION_DATE, "source_url": ROSTER_URL,
            "next_offset": offset + limit if offset + limit < len(matches) else None}
