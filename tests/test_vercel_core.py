from api import index as api_index


def test_core_company_uses_dict_rows_and_fails_open_on_director_error(monkeypatch):
    def fake_filter(api, field, value, top):
        if api == api_index.COMPANY_API:
            return [{
                "Business_Accounting_NO": value,
                "Company_Name": "測試股份有限公司",
            }]
        raise RuntimeError("director upstream unavailable")

    monkeypatch.setattr(api_index, "_company_filter", fake_filter)
    monkeypatch.setattr(
        api_index,
        "_local_context",
        lambda uniform: {
            "configured": True,
            "evidence": [],
            "evidence_count": 0,
            "company": None,
        },
    )
    data = api_index.core_company("12345678")
    assert data["status"] == "ok"
    assert data["company_name"] == "測試股份有限公司"
    assert data["people"] == []
    assert data["graph"]["edges"] == []
    assert data["evidence_status"]["董監事"]["status"] == "partial"


def test_core_company_does_not_call_public_evidence_collector(monkeypatch):
    calls = {"company": 0, "director": 0}

    def fake_filter(api, field, value, top):
        if api == api_index.COMPANY_API:
            calls["company"] += 1
            return [{"Company_Name": "隔離測試公司"}]
        calls["director"] += 1
        return [{"Person_Name": "測試董事", "Person_Position_Name": "董事"}]

    monkeypatch.setattr(api_index, "_company_filter", fake_filter)
    monkeypatch.setattr(
        api_index,
        "_local_context",
        lambda uniform: {"configured": False, "evidence": [], "evidence_count": 0},
    )
    data = api_index.core_company("87654321")
    assert data["company_name"] == "隔離測試公司"
    assert calls == {"company": 1, "director": 1}
    assert len(data["people"]) == 1
