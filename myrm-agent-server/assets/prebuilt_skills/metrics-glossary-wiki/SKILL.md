---
name: metrics-glossary-wiki
description: "Crystallize ambiguous business metrics, KPIs, and domain terminology into authoritative, disambiguated LLM-Wiki knowledge base articles with formal computation formulas and cross-linked concepts."
version: "1.0.0"
category: "data-analysis"
tags:
  - metrics
  - glossary
  - wiki
  - data-governance
  - kpi
  - disambiguation
  - knowledge-base
allowed-tools:
  - wiki_ingest_tool
  - wiki_query_tool
  - wiki_apply_tool
  - file_write_tool
  - file_read_tool
---

# Metrics Glossary & KPI Wiki Crystallization (指标口径与业务词汇 Wiki 结晶包)

## Overview

This skill establishes an authoritative data governance and knowledge crystallization workflow.
It eliminates the critical enterprise problem of **metric ambiguity and duplicate definitions** (e.g. GMV gross vs net, active user heartbeat vs interaction, churn windows) by distilling discussions, data dictionaries, and SQL formulas into structured, cross-linked LLM-Wiki concepts (`wiki/concepts/metric_*.md`).

---

## 1. The 5-Dimension Metric Definition Card Standard

Every crystallized metric article must adhere to the following schema:

```markdown
---
concept: "metric_gmv_net"
aliases:
  - "净成交总额"
  - "Net GMV"
category: "financial_metrics"
owners:
  - "财务部"
  - "商业化分析组"
status: "authoritative"
updated_at: "2026-09-10"
---

# 净成交总额 (Net GMV)

## 1. 业务定义 (Business Definition)
统计周期内，用户成功下单并完成支付、且在 T+7 无条件退款期结束后未发生退款的商品与服务结算净总额。

## 2. 统计边界与排除项 (Inclusions & Exclusions)
- **包含**: 优惠券抵扣前实际支付金额、用户承担运费、增值税。
- **排除**: 未支付订单、支付即撤单、T+7 内全额退款、平台虚拟刷单/测试订单。

## 3. 标准计算公式 / SQL 逻辑 (Formula & SQL)
\[
\text{Net GMV} = \sum (\text{order\_paid\_amount}) - \sum (\text{refund\_amount}_{\text{T+7}})
\]

```sql
SELECT 
  DATE_TRUNC('month', payment_time) AS report_month,
  SUM(paid_amount - COALESCE(refund_amount_7d, 0)) AS net_gmv
FROM dwd_orders_fact
WHERE is_valid = 1 
  AND payment_status = 'SUCCESS'
GROUP BY 1;
```

## 4. 相关概念与血缘网络 (Related Concepts & Lineage)
- 上游基础指标: [[metric_gmv_gross]] (毛成交总额)
- 下游衍生指标: [[metric_take_rate]] (货币化率 / 抽成率)
- 关联维度: [[dim_platform_channel]], [[dim_user_tier]]
```

---

## 2. Metric Disambiguation Protocol (指标消歧与防打架规约)

When encountering ambiguous user prompts (e.g. *"Show me this month's GMV"*):

1. **Pre-flight Wiki Query**:
   Agent executes `wiki_query_tool(query="GMV 口径")` to verify if multiple definitions exist (e.g. `metric_gmv_gross` vs `metric_gmv_net`).
2. **Surface Clarification**:
   If ambiguity exists, explicitly inform the user of the canonical choices:
   - *"当前存在两种指标口径：① 毛成交额 (GMV Gross，含退款) 与 ② 净成交额 (GMV Net，扣除 T+7 退款)。默认采用权威财务口径 ② 进行统计，如需毛额请说明。"*
3. **Automatic Wiki Ingestion**:
   When new definitions are agreed upon in conversation, invoke `wiki_ingest_tool` to crystallize the newly defined metric into `wiki/raw/` and auto-compile into `wiki/concepts/`.

---

## 3. Verification Checklist

Before publishing or executing queries against a metric:
- [ ] Is the formula or SQL definition deterministic and copy-paste reproducible?
- [ ] Are exclusions (refunds, cancellations, internal test data) explicitly stated?
- [ ] Are wiki-links `[[metric_*]]` established to connect dependent parent/child metrics?
- [ ] Does the concept file contain frontmatter metadata (`concept`, `category`, `owners`)?
