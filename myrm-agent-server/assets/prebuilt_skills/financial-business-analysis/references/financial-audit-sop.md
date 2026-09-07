# Financial Audit, Reconciliation & Source Verification SOP

## 1. Official Disclosure Whitelist & Retrieval Strategy

When conducting corporate and financial research, always prioritize Tier-1 official disclosures. Avoid relying on third-party secondary blog posts or unverified aggregators.

### 1.1 Priority Source Whitelist

| Market / Region | Tier-1 Official Repository | Query & Retrieval Strategy |
| :--- | :--- | :--- |
| **US Equities (SEC)** | **SEC EDGAR** (`sec.gov/edgar`) | Target `10-K` (Annual), `10-Q` (Quarterly), `8-K` (Material events), `S-1` (Prospectus) |
| **China A-Shares (A股)** | **CnInfo (巨潮资讯网)** (`cninfo.com.cn`) | Target 年度报告 / 半年度报告 / 招股说明书 / 业绩预告 |
| **Hong Kong (港股)** | **HKEXnews (披露易)** (`hkexnews.hk`) | Target 年报 / 中期报告 / 全球发售招股书 |
| **Global / Corporate IR** | **Official Company Investor Relations (IR)** | Target Official Earnings Release PDF, Webcast Presentation Slides, Shareholder Letter |

---

## 2. Sandbox Python 3-Statement Reconciliation Algorithm

To eliminate arithmetic hallucinations, execute a standard Python verification script inside the sandbox environment via `bash_code_execute_tool`.

### 2.1 Standard Verification Script Pattern

```python
"""
Python Financial Reconciliation Script (Sample Template)
"""
import json

def audit_three_statements(data: dict) -> dict:
    results = {
        "balance_sheet_balanced": False,
        "cash_flow_reconciled": False,
        "metrics": {},
        "discrepancies": []
    }
    
    # 1. Balance Sheet Identity
    assets = data["balance_sheet"]["total_assets"]
    liabilities = data["balance_sheet"]["total_liabilities"]
    equity = data["balance_sheet"]["total_equity"]
    bs_diff = abs(assets - (liabilities + equity))
    
    if bs_diff < 1.0:  # Allowing rounding tolerance of 1 unit
        results["balance_sheet_balanced"] = True
    else:
        results["discrepancies"].append(
            f"Balance Sheet Discrepancy: Assets ({assets}) != Liab + Equity ({liabilities + equity}), Diff = {bs_diff}"
        )
        
    # 2. Free Cash Flow & Cash Reconciliation
    ocf = data["cash_flow"]["operating_cash_flow"]
    capex = data["cash_flow"]["capital_expenditures"]
    fcf = ocf - capex
    results["metrics"]["free_cash_flow"] = fcf
    
    # 3. DuPont 3-Factor Ratios
    net_income = data["income_statement"]["net_income"]
    revenue = data["income_statement"]["total_revenue"]
    
    net_profit_margin = net_income / revenue if revenue else 0.0
    asset_turnover = revenue / assets if assets else 0.0
    equity_multiplier = assets / equity if equity else 0.0
    calc_roe = net_profit_margin * asset_turnover * equity_multiplier
    
    results["metrics"]["net_profit_margin"] = round(net_profit_margin * 100, 2)
    results["metrics"]["asset_turnover"] = round(asset_turnover, 3)
    results["metrics"]["equity_multiplier"] = round(equity_multiplier, 3)
    results["metrics"]["calculated_roe"] = round(calc_roe * 100, 2)
    
    return results
```

---

## 3. Currency & Unit Normalization Rules

1. **Standard Base Currency**: Always declare the reporting base currency in the header (e.g., `USD`, `RMB`, `EUR`). If comparing multi-currency peers, specify foreign exchange conversion rates used.
2. **Explicit Unit Scale**: Explicitly specify unit magnitude (e.g., `in Millions (M)` or `in Billions (B)` / `万元` / `亿元`). Never mix units across table columns without explicit row labels.
3. **Fiscal Year Alignment**: Explicitly state fiscal year convention (e.g., Apple FY ends in September; Microsoft FY ends in June; standard calendar year ends Dec 31).

---

## 4. Non-Public Startup / Private Company Qualitative Fallback SOP

When the target company is an unlisted startup without public regulatory 10-K/annual filings:

1. **Gate Activation**: Do NOT attempt to fabricate synthetic balance sheets or hallucinate net profit numbers.
2. **Shift to Unit Economics & Market Moat**:
   - Primary data sources: Official PR, Crunchbase/ITJuzi funding rounds, patent filings, public customer case studies, product pricing pages.
   - Core analysis vectors:
     - **Funding History & Valuation Trajectory**: Seed -> Series A/B/C investors and post-money valuations.
     - **Unit Economics Model (CAC, LTV, Gross Margin Proxy)**.
     - **TAM / SAM / SOM & Competitive Displacement**: Which incumbent market share is targeted.
3. **Explicit Disclosure Tag**: Add mandatory advisory badge at the top of the report:
   > ⚠️ `[Non-Public Entity Note]`: Target company is unlisted. Analysis is derived from verified public disclosures, verified funding records, and industry benchmark proxies. Audited 3-statement financials are not publicly available.
