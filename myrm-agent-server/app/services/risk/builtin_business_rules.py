"""The built-in risk rules for business and compliance content: company, customer, finance and legal, political.

[INPUT]
- .constants::RiskCategory, RiskSeverity, RuleSeed (POS: Vocabulary of rule severity and category.)
- .patterns::keyword_pattern (POS: Builds a whole-word keyword pattern.)

[OUTPUT]
- BUSINESS_RULES: the seed definitions of the rules outside the personal and security categories

[POS]
Organisation names, contracts, budgets and similar topics are everyday subjects of an assistant, so none of these rules
starts enabled (see ``DEFAULT_ENABLED_CATEGORIES``); a user turns on the ones their own data calls for.
"""

from __future__ import annotations

from .constants import RiskCategory, RiskSeverity, RuleSeed
from .patterns import keyword_pattern

BUSINESS_RULES: list[RuleSeed] = [
    # ── Company Internal ──
    {
        "rule_id": "private_ip",
        "display_name": "Private network address",
        "description": "Detect RFC1918 private IP addresses.",
        "pattern": r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b",
        "severity": RiskSeverity.MEDIUM,
        "category": RiskCategory.COMPANY,
        "sort_order": 200,
    },
    {
        "rule_id": "internal_domain_name",
        "display_name": "Internal domain or system hostname",
        "description": "Detect common internal domain and system naming patterns.",
        "pattern": r"(?i)\b(?:corp|internal|intra|intranet|gitlab|jenkins|confluence|jira|wiki|oa|vpn)\.[a-z0-9.-]+\b",
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.COMPANY,
        "sort_order": 210,
    },
    {
        "rule_id": "internal_hostname_pattern",
        "display_name": "Internal host or environment naming",
        "description": "Detect internal hostnames and environment-specific resource names.",
        "pattern": r"(?i)\b(?:prod|stg|stage|dev|test|uat|db|redis|mq|k8s|kube|es|kafka|mongo|mysql|postgres)[-_][a-z0-9.-]+\b",
        "severity": RiskSeverity.MEDIUM,
        "category": RiskCategory.COMPANY,
        "sort_order": 220,
    },
    {
        "rule_id": "kubernetes_service_dns",
        "display_name": "Kubernetes service DNS",
        "description": "Detect Kubernetes internal service DNS references.",
        "pattern": r"(?i)\b[a-z0-9-]+\.[a-z0-9-]+\.svc(?:\.cluster\.local)?\b",
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.COMPANY,
        "sort_order": 230,
    },
    {
        "rule_id": "project_codename_keywords",
        "display_name": "Project codename or roadmap wording",
        "description": "Detect project codename or unreleased roadmap wording.",
        "pattern": keyword_pattern("项目代号", "产品代号", "代号", "codename", "roadmap", "未发布", "未公开", "internal launch"),
        "severity": RiskSeverity.MEDIUM,
        "category": RiskCategory.COMPANY,
        "sort_order": 240,
    },
    {
        "rule_id": "org_roster_keywords",
        "display_name": "Organization roster or directory",
        "description": "Detect organization charts, rosters, and internal directories.",
        "pattern": keyword_pattern(
            "组织架构",
            "员工名单",
            "花名册",
            "通讯录",
            "organization chart",
            "employee roster",
            "staff roster",
            "employee directory",
            "staff directory",
        ),
        "severity": RiskSeverity.MEDIUM,
        "category": RiskCategory.COMPANY,
        "sort_order": 250,
    },
    {
        "rule_id": "salary_hr_keywords",
        "display_name": "Salary or HR data",
        "description": "Detect compensation, payroll, and HR evaluation wording.",
        "pattern": keyword_pattern(
            "薪资", "薪酬", "绩效", "KPI", "晋升", "调薪", "裁员", "salary", "compensation", "payroll", "performance review"
        ),
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.COMPANY,
        "sort_order": 260,
    },
    # ── Customer Data ──
    {
        "rule_id": "customer_list_keywords",
        "display_name": "Customer list or contact list",
        "description": "Detect customer roster and contact-list style wording.",
        "pattern": keyword_pattern(
            "客户名单", "客户列表", "联系人清单", "CRM导出", "customer list", "client list", "contact list", "lead list"
        ),
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.CUSTOMER,
        "sort_order": 300,
    },
    {
        "rule_id": "contract_quote_keywords",
        "display_name": "Contract or quote document",
        "description": "Detect contract, quotation, or tender document wording.",
        "pattern": keyword_pattern(
            "合同",
            "报价单",
            "投标",
            "采购单",
            "订单明细",
            "contract",
            "quote",
            "quotation",
            "proposal",
            "tender",
            "purchase order",
            "order details",
        ),
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.CUSTOMER,
        "sort_order": 310,
    },
    {
        "rule_id": "crm_ticket_keywords",
        "display_name": "CRM or ticket data",
        "description": "Detect CRM notes, ticket content, or customer profile wording.",
        "pattern": keyword_pattern(
            "工单", "客服记录", "客户画像", "客户需求", "ticket", "case record", "crm note", "customer profile"
        ),
        "severity": RiskSeverity.MEDIUM,
        "category": RiskCategory.CUSTOMER,
        "sort_order": 320,
    },
    # ── Finance & Legal ──
    {
        "rule_id": "financial_metrics_keywords",
        "display_name": "Financial metrics or budget data",
        "description": "Detect financial metrics, budgets, and profitability wording.",
        "pattern": keyword_pattern(
            "营收",
            "收入",
            "利润",
            "毛利",
            "成本",
            "预算",
            "现金流",
            "revenue",
            "gross margin",
            "profit",
            "budget",
            "cash flow",
        ),
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.FINANCE_LEGAL,
        "sort_order": 400,
    },
    {
        "rule_id": "invoice_tax_keywords",
        "display_name": "Invoice or tax information",
        "description": "Detect invoice and tax identifier wording.",
        "pattern": keyword_pattern("发票", "税号", "纳税识别号", "开票信息", "invoice", "tax id", "vat", "tin"),
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.FINANCE_LEGAL,
        "sort_order": 410,
    },
    {
        "rule_id": "legal_document_keywords",
        "display_name": "Legal or compliance document",
        "description": "Detect legal opinions, disputes, and NDA style wording.",
        "pattern": keyword_pattern(
            "法务意见",
            "诉讼",
            "仲裁",
            "保密协议",
            "NDA",
            "legal opinion",
            "litigation",
            "arbitration",
            "non-disclosure agreement",
        ),
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.FINANCE_LEGAL,
        "sort_order": 420,
    },
    # ── Political & Military ──
    {
        "rule_id": "political_person_org_keywords",
        "display_name": "Political or government organization wording",
        "description": "Detect political institutions, officials, and related wording.",
        "pattern": keyword_pattern(
            "国务院",
            "外交部",
            "国安",
            "公安部",
            "人大",
            "政协",
            "党中央",
            "中央军委",
            "政府工作报告",
            "政治局",
            "state council",
            "ministry of foreign affairs",
            "national security",
        ),
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.POLITICAL,
        "sort_order": 500,
    },
    {
        "rule_id": "military_security_keywords",
        "display_name": "Military or national security wording",
        "description": "Detect military deployment, weapons, and national security wording.",
        "pattern": keyword_pattern(
            "军事部署",
            "武器系统",
            "导弹",
            "军工",
            "部队番号",
            "国家安全",
            "涉密单位",
            "military deployment",
            "weapon system",
            "missile",
            "classified unit",
        ),
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.POLITICAL,
        "sort_order": 510,
    },
    {
        "rule_id": "extremism_keywords",
        "display_name": "Extremism or violent attack wording",
        "description": "Detect extremist, violent attack, and bomb-making wording.",
        "pattern": keyword_pattern(
            "恐怖袭击", "炸弹制造", "极端组织", "暴恐", "terrorist attack", "bomb making", "extremist organization"
        ),
        "severity": RiskSeverity.HIGH,
        "category": RiskCategory.POLITICAL,
        "sort_order": 520,
    },
]
