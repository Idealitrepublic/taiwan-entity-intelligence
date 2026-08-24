"""Taiwan Ministry of Economic Affairs company basic-data client."""

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

API_URL = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"


def get_company(uniform_number: str, timeout: int = 15) -> Optional[Dict[str, Any]]:
    params = {
        "$format": "json",
        "$filter": "Business_Accounting_NO eq {}".format(uniform_number),
        "$skip": "0",
        "$top": "1",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "TaiwanEntityIntelligence/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data[0] if data else None
