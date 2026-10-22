# Verified company source links — Development scope

This change strengthens read projections; it does **not** bulk-publish historical
penalties, judgments, or awards and does not alter Production or Supabase schema.
The canonical Development company index has 462 published company IDs; that is
not the population of all Taiwan companies or a guarantee of source coverage.

## Official company ID ↔ domain crosswalk

`src/company_website_crosswalk.json` holds five reviewed pairs. Every row carries
the exact eight-digit company ID, full current company name, HTTPS website,
identity proof, website proof, verification basis, and review date. The runtime
uses a row only when the live MOEA company name **and** ID agree. A conflicting
registry website disables automatic 165 comparison until reviewed. A missing
crosswalk row means unknown, not no website.

| ID | Company | Reviewed domain | Primary identity / website proof |
| --- | --- | --- | --- |
| 04231910 | 國泰世華商業銀行股份有限公司 | cathaybk.com.tw | [Bank's own about page](https://www.cathaybk.com.tw/cathaybk/personal/about/brand/intro/) lists the uniform number and company name. |
| 96979933 | 中華電信股份有限公司 | cht.com.tw | [Company service page](https://www.cht.com.tw/home/campaign/prepaidcard/intro) lists the company and uniform number. |
| 23060248 | 全家便利商店股份有限公司 | family.com.tw | [Company-hosted document](https://www.family.com.tw/Web_EnterPrise/PDFWebShow.ashx?ID=202351&Lagu=0) lists the company and uniform number. |
| 22099131 | 台灣積體電路製造股份有限公司 | tsmc.com | [Government employment listing](https://job.taiwanjobs.gov.tw/internet/jobwanted/company_desc2.aspx?BRANCH_ID=&EMPLOYER_ID=569) identifies the company and uniform number; [company profile](https://www.tsmc.com/chinese/aboutTSMC/company_profile) identifies the official site. |
| 22555003 | 統一超商股份有限公司 | 7-11.com.tw | [Company investor-relations profile](https://ir.7-11.com.tw/tw/companyprofile.php) lists company name and uniform number. |

The 165 check is an **exact domain match in the indexed snapshot**, not a safety
certification or a finding against the company. The UI exposes the website proof
beside the check result. The remaining company domains must be sourced and
reviewed individually; no site is inferred from a name or search result.

## Penalties, judgments, procurement

- Labor source rows with an explicit ID conflicting with the queried company
  are excluded from its live candidate projection. Name-only rows remain
  visible as unverified candidates, not canonical Relationships. The indexed
  labor dataset currently has almost no company IDs, so bulk publication would
  be unsafe without independent official row-level identity evidence.
- Judicial JDoc name matching now requires equality of the normalized **full
  extracted company name** rather than substring inclusion. Even an exact
  name mention does not prove party role, liability, or canonical company ID;
  it stays a source-scoped observation until the official document establishes
  an independently reviewable identity and role.
- Procurement mirror results require an exact bidder ID and a single,
  non-contradictory winner role. Mixed winner/nonwinner paths for the same name
  are unresolved. Mirror results remain live observations; a published
  Relationship still requires matching the original PCC notice, case locator,
  exact bidder ID, winner role, amount, date, and primary Evidence.

## Verification and rollback

Run `python -m unittest tests.test_verified_company_source_links
tests.test_165_domain_check tests.test_judicial_coverage
tests.test_procurement_materialization tests.test_labor_materialization`.
The crosswalk and rule changes are reversible by reverting this commit. No
database migration or existing source record must be rolled back. Re-check
official pages periodically: ownership or domain changes require re-review,
not automatic substitution.
