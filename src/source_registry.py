"""Canonical registry of evidence sources used by Taiwan Entity Intelligence."""

SOURCES = {
    "judicial": {
        "name": "司法院裁判書開放 API",
        "source_type": "judicial",
        "fact_type": "court_record",
        "official_url": "https://opendata.judicial.gov.tw/",
        "access": "api_token",
        "note": "API requires an account/token; records may be updated or removed.",
    },
    "procurement": {
        "name": "政府電子採購／標案資料",
        "source_type": "procurement",
        "fact_type": "government_tender",
        "official_url": "https://data.gov.tw/",
        "access": "open_data_or_local_import",
    },
    "penalty": {
        "name": "政府機關行政裁罰資料",
        "source_type": "administrative_penalty",
        "fact_type": "administrative_penalty",
        "official_url": "https://data.gov.tw/",
        "access": "open_data_or_local_import",
        "note": "Multiple agencies publish separate penalty datasets; preserve issuing agency as provenance.",
    },
    "fraud": {
        "name": "政府反詐／涉詐警示資料",
        "source_type": "fraud_signal",
        "fact_type": "fraud_signal",
        "official_url": "https://data.gov.tw/",
        "access": "open_data_or_local_import",
        "note": "A fraud signal is not a finding of wrongdoing; keep the original source and status.",
    },
}
