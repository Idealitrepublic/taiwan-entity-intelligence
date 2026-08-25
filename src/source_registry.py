"""Canonical registry of evidence sources used by Taiwan Entity Intelligence."""

SOURCES = {
    "judicial": {
        "name": "司法院裁判書開放 API",
        "source_type": "judicial",
        "fact_type": "court_record",
        "official_url": "https://opendata.judicial.gov.tw/",
        "access": "api_token",
        "incremental": "7-day change list",
        "note": "API requires an account/token; records can be updated or removed and must be replaced/removed by jid.",
    },
    "procurement": {
        "name": "政府電子採購／標案資料",
        "source_type": "procurement",
        "fact_type": "government_tender",
        "official_url": "https://data.gov.tw/",
        "access": "open_data_or_local_import",
    },
    "penalty": {
        "name": "政府機關行政裁罰資料（自動探索）",
        "source_type": "administrative_penalty",
        "fact_type": "administrative_penalty",
        "official_url": "https://data.gov.tw/",
        "access": "open_data_catalog_discovery",
        "discovery_keywords": ["裁罰", "裁處", "罰鍰", "行政處分", "處分名單"],
        "note": "Discovers entity-level public datasets by title/metadata. Statistical-only datasets are excluded; source agency remains provenance.",
    },
    "fraud_165_blocked": {
        "name": "165 遭停止解析涉詐網站",
        "source_type": "fraud_signal",
        "fact_type": "fraud_signal",
        "official_url": "https://data.gov.tw/dataset/176455",
        "access": "open_data",
        "incremental": "content-addressed dedup",
    },
    "fraud_165_rumors": {
        "name": "165 詐騙闢謠專區",
        "source_type": "fraud_signal",
        "fact_type": "fraud_signal",
        "official_url": "https://data.gov.tw/dataset/38262",
        "access": "open_data",
        "incremental": "content-addressed dedup",
    },
    "fraud_165_fake_investment": {
        "name": "165 假投資／博弈網站",
        "source_type": "fraud_signal",
        "fact_type": "fraud_signal",
        "official_url": "https://data.gov.tw/dataset/160055",
        "access": "open_data",
        "incremental": "content-addressed dedup",
    },
}
