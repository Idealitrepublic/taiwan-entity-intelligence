import json
import urllib.parse
import urllib.request

API_URL = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"


def get_company_data(uniform_number):
    params = {
        "$format": "json",
        "$filter": "Business_Accounting_NO eq '{}'".format(uniform_number),
        "$skip": "0",
        "$top": "1"
    }

    url = API_URL + "?" + urllib.parse.urlencode(params)

    print()
    print("正在查詢經濟部商工行政資料...")
    print("統一編號：", uniform_number)

    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        if not data:
            print()
            print("找不到這家公司。")
            return None

        company = data[0]

        print()
        print("=" * 50)
        print("TAIWAN ENTITY INTELLIGENCE")
        print("=" * 50)

        print("公司名稱：", company.get("Company_Name", "N/A"))
        print("統一編號：", company.get("Business_Accounting_NO", "N/A"))
        print("公司狀態：", company.get("Company_Status_Desc", "N/A"))
        print("負責人：", company.get("Responsible_Name", "N/A"))
        print("資本額：", company.get("Capital_Stock_Amount", "N/A"))
        print("實收資本額：", company.get("Paid_In_Capital_Amount", "N/A"))
        print("公司地址：", company.get("Company_Location", "N/A"))
        print("設立日期：", company.get("Company_Setup_Date", "N/A"))

        print("=" * 50)

        return company

    except Exception as error:
        print()
        print("查詢發生錯誤：")
        print(error)
        return None


if __name__ == "__main__":
    uniform_number = input("請輸入公司統一編號：").strip()

    if uniform_number.isdigit():
        get_company_data(uniform_number)
    else:
        print("請輸入純數字的統一編號。")
