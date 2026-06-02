"""Risk rule constants and built-in rule definitions.

Severity levels: low / medium / high
Actions: allow / block
Categories: personal / company / security / finance_legal / political / customer
"""

from __future__ import annotations


class RiskSeverity:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    RANK = {LOW: 1, MEDIUM: 2, HIGH: 3}


class RiskAction:
    ALLOW = "allow"
    BLOCK = "block"

    RANK = {ALLOW: 1, BLOCK: 2}


class RiskCategory:
    PERSONAL = "personal"
    COMPANY = "company"
    SECURITY = "security"
    FINANCE_LEGAL = "finance_legal"
    POLITICAL = "political"
    CUSTOMER = "customer"
    CUSTOM = "custom"


def builtin_risk_rules() -> list[dict[str, str | int | bool]]:
    """Return the 31 built-in risk rule seed definitions."""
    return [
        # ── Personal Information ──
        {
            "rule_id": "email_address",
            "display_name": "Email address",
            "description": "Detect email addresses.",
            "pattern": r"(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 10,
        },
        {
            "rule_id": "cn_mobile_number",
            "display_name": "Chinese mainland mobile number",
            "description": "Detect Chinese mainland mobile phone numbers.",
            "pattern": r"(?:\+?86[- ]?)?1[3-9]\d{9}",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 20,
        },
        {
            "rule_id": "cn_id_card",
            "display_name": "Chinese ID card number",
            "description": "Detect 18-digit Chinese ID card numbers.",
            "pattern": r"\b\d{17}[\dXx]\b",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 30,
        },
        {
            "rule_id": "passport_number",
            "display_name": "Passport number",
            "description": "Detect common passport number formats.",
            "pattern": r"(?i)\b(?:passport|护照)[^A-Za-z0-9]{0,12}[A-Z0-9]{7,10}\b",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 40,
        },
        {
            "rule_id": "bank_card_context",
            "display_name": "Bank card context",
            "description": "Detect card-number-like data near bank-card keywords.",
            "pattern": r"(?i)(银行卡|bank card|card number|account number).{0,24}\b\d(?:[ -]?\d){11,18}\b",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 50,
        },
        {
            "rule_id": "personal_address_keywords",
            "display_name": "Personal address keywords",
            "description": "Detect common personal address expressions.",
            "pattern": r"(?i)(住址|开户地址|通信地址|家庭住址|收件地址|mailing address|home address|residential address)",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 60,
        },
        {
            "rule_id": "resume_cv_keywords",
            "display_name": "Resume or CV content",
            "description": "Detect resume and curriculum vitae related content.",
            "pattern": r"(?i)\b(简历|履历|resume|curriculum vitae|work experience|employment history|education history|expected salary)\b",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 70,
        },
        # ── Security Credentials ──
        {
            "rule_id": "private_key_marker",
            "display_name": "Private key material",
            "description": "Detect PEM private key markers.",
            "pattern": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 100,
        },
        {
            "rule_id": "api_key_like",
            "display_name": "API key or cloud credential pattern",
            "description": "Detect common API key and cloud credential patterns.",
            "pattern": r"(?i)\b(sk-[a-z0-9]{12,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|ghp_[0-9A-Za-z]{20,255}|AIza[0-9A-Za-z\-_]{35})\b",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 110,
        },
        {
            "rule_id": "credential_assignment",
            "display_name": "Credential assignment pattern",
            "description": "Detect explicit password, secret, token, or API key assignment.",
            "pattern": r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token|client[_-]?secret|access[_-]?key)\b\s*[:=]\s*\S+",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 120,
        },
        {
            "rule_id": "jwt_token_like",
            "display_name": "JWT token",
            "description": "Detect JWT-like bearer tokens.",
            "pattern": r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 130,
        },
        {
            "rule_id": "cookie_session_like",
            "display_name": "Cookie or session secret wording",
            "description": "Detect session, cookie, and authorization wording.",
            "pattern": r"(?i)\b(sessionid|set-cookie|refresh_token|access_token|authorization|cookie)\b",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 140,
        },
        {
            "rule_id": "db_connection_string",
            "display_name": "Database or queue connection string",
            "description": "Detect connection strings for databases, caches, and queues.",
            "pattern": r"(?i)\b(?:mysql|postgres(?:ql)?|mongodb(?:\+srv)?|redis|amqp|kafka):\/\/[^\s]+",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 150,
        },
        {
            "rule_id": "kubeconfig_content",
            "display_name": "Kubeconfig content",
            "description": "Detect kubeconfig-style configuration content.",
            "pattern": r"(?s)apiVersion:\s*v1.{0,400}(clusters:|contexts:|users:)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 160,
        },
        {
            "rule_id": "env_file_secret",
            "display_name": "Environment secret variable",
            "description": "Detect common secret variable names in env-style content.",
            "pattern": r"(?i)\b(DATABASE_URL|SECRET_KEY|PRIVATE_KEY|ACCESS_KEY|API_SECRET|CLIENT_SECRET|WEBHOOK_SECRET)\b",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 170,
        },
        # ── Company Internal ──
        {
            "rule_id": "private_ip",
            "display_name": "Private network address",
            "description": "Detect RFC1918 private IP addresses.",
            "pattern": r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.COMPANY,
            "sort_order": 200,
        },
        {
            "rule_id": "internal_domain_name",
            "display_name": "Internal domain or system hostname",
            "description": "Detect common internal domain and system naming patterns.",
            "pattern": r"(?i)\b(?:corp|internal|intra|intranet|gitlab|jenkins|confluence|jira|wiki|oa|vpn)\.[a-z0-9.-]+\b",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.COMPANY,
            "sort_order": 210,
        },
        {
            "rule_id": "internal_hostname_pattern",
            "display_name": "Internal host or environment naming",
            "description": "Detect internal hostnames and environment-specific resource names.",
            "pattern": r"(?i)\b(?:prod|stg|stage|dev|test|uat|db|redis|mq|k8s|kube|es|kafka|mongo|mysql|postgres)[-_][a-z0-9.-]+\b",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.COMPANY,
            "sort_order": 220,
        },
        {
            "rule_id": "kubernetes_service_dns",
            "display_name": "Kubernetes service DNS",
            "description": "Detect Kubernetes internal service DNS references.",
            "pattern": r"(?i)\b[a-z0-9-]+\.[a-z0-9-]+\.svc(?:\.cluster\.local)?\b",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.COMPANY,
            "sort_order": 230,
        },
        {
            "rule_id": "project_codename_keywords",
            "display_name": "Project codename or roadmap wording",
            "description": "Detect project codename or unreleased roadmap wording.",
            "pattern": r"(?i)(项目代号|产品代号|代号|codename|roadmap|未发布|未公开|internal launch)",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.COMPANY,
            "sort_order": 240,
        },
        {
            "rule_id": "org_roster_keywords",
            "display_name": "Organization roster or directory",
            "description": "Detect organization charts, rosters, and internal directories.",
            "pattern": r"(?i)(组织架构|员工名单|花名册|通讯录|organization chart|employee roster|staff roster|directory)",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.COMPANY,
            "sort_order": 250,
        },
        {
            "rule_id": "salary_hr_keywords",
            "display_name": "Salary or HR data",
            "description": "Detect compensation, payroll, and HR evaluation wording.",
            "pattern": r"(?i)(薪资|薪酬|绩效|KPI|晋升|调薪|裁员|salary|compensation|payroll|performance review)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.COMPANY,
            "sort_order": 260,
        },
        # ── Customer Data ──
        {
            "rule_id": "customer_list_keywords",
            "display_name": "Customer list or contact list",
            "description": "Detect customer roster and contact-list style wording.",
            "pattern": r"(?i)(客户名单|客户列表|联系人清单|CRM导出|customer list|client list|contact list|lead list)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.CUSTOMER,
            "sort_order": 300,
        },
        {
            "rule_id": "contract_quote_keywords",
            "display_name": "Contract or quote document",
            "description": "Detect contract, quotation, or tender document wording.",
            "pattern": r"(?i)(合同|报价单|投标|采购单|订单明细|contract|quote|quotation|proposal|tender|purchase order|order details)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.CUSTOMER,
            "sort_order": 310,
        },
        {
            "rule_id": "crm_ticket_keywords",
            "display_name": "CRM or ticket data",
            "description": "Detect CRM notes, ticket content, or customer profile wording.",
            "pattern": r"(?i)(工单|客服记录|客户画像|客户需求|ticket|case record|crm note|customer profile)",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.CUSTOMER,
            "sort_order": 320,
        },
        # ── Finance & Legal ──
        {
            "rule_id": "financial_metrics_keywords",
            "display_name": "Financial metrics or budget data",
            "description": "Detect financial metrics, budgets, and profitability wording.",
            "pattern": r"(?i)(营收|收入|利润|毛利|成本|预算|现金流|revenue|gross margin|profit|budget|cash flow)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.FINANCE_LEGAL,
            "sort_order": 400,
        },
        {
            "rule_id": "invoice_tax_keywords",
            "display_name": "Invoice or tax information",
            "description": "Detect invoice and tax identifier wording.",
            "pattern": r"(?i)(发票|税号|纳税识别号|开票信息|invoice|tax id|vat|tin)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.FINANCE_LEGAL,
            "sort_order": 410,
        },
        {
            "rule_id": "legal_document_keywords",
            "display_name": "Legal or compliance document",
            "description": "Detect legal opinions, disputes, and NDA style wording.",
            "pattern": r"(?i)(法务意见|诉讼|仲裁|保密协议|NDA|legal opinion|litigation|arbitration|non-disclosure agreement)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.FINANCE_LEGAL,
            "sort_order": 420,
        },
        # ── Political & Military ──
        {
            "rule_id": "political_person_org_keywords",
            "display_name": "Political or government organization wording",
            "description": "Detect political institutions, officials, and related wording.",
            "pattern": r"(?i)(国务院|外交部|国安|公安部|人大|政协|党中央|中央军委|政府工作报告|政治局|state council|ministry of foreign affairs|national security)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.POLITICAL,
            "sort_order": 500,
        },
        {
            "rule_id": "military_security_keywords",
            "display_name": "Military or national security wording",
            "description": "Detect military deployment, weapons, and national security wording.",
            "pattern": r"(?i)(军事部署|武器系统|导弹|军工|部队番号|国家安全|涉密单位|military deployment|weapon system|missile|classified unit)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.POLITICAL,
            "sort_order": 510,
        },
        {
            "rule_id": "extremism_keywords",
            "display_name": "Extremism or violent attack wording",
            "description": "Detect extremist, violent attack, and bomb-making wording.",
            "pattern": r"(?i)(恐怖袭击|炸弹制造|极端组织|暴恐|terrorist attack|bomb making|extremist organization)",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.POLITICAL,
            "sort_order": 520,
        },
    ]
