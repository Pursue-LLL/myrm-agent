"""The built-in risk rule definitions.

[INPUT]
- .constants::RiskAction, RiskCategory, RiskSeverity (POS: Vocabulary of rule severity, action and category.)
- .builtin_business_rules::BUSINESS_RULES (POS: The seed definitions of the business and compliance rules.)
- .patterns (POS: The pattern builders and shared pattern parts the rules are written with.)
- myrm_agent_harness.core.security.detection (POS: The privacy detectors' own patterns for e-mail, mobile number, ID card and bank card.)

[OUTPUT]
- builtin_risk_rules: the seed definition of every built-in rule

[POS]
The e-mail, mobile number, ID card and bank card rules use the privacy detectors' own patterns, so the channel gate and
the privacy classifier read the same data the same way. Which categories start enabled is ``DEFAULT_ENABLED_CATEGORIES``.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.detection.card_context import CARD_CONTEXT_RE
from myrm_agent_harness.core.security.detection.pii_patterns import CHINA_ID_RE, CHINA_PHONE_RE, EMAIL_RE

from .builtin_business_rules import BUSINESS_RULES
from .constants import RiskAction, RiskCategory, RiskSeverity, RuleSeed
from .patterns import API_KEY_PATTERN, ASSIGNED_VALUE, ASSIGNMENT_OPERATOR, detector_pattern, keyword_pattern


def builtin_risk_rules() -> list[RuleSeed]:
    """Return the 31 built-in risk rule seed definitions."""
    personal_and_security: list[RuleSeed] = [
        # ── Personal Information ──
        {
            "rule_id": "email_address",
            "display_name": "Email address",
            "description": "Detect email addresses.",
            "pattern": detector_pattern(EMAIL_RE),
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 10,
        },
        {
            "rule_id": "cn_mobile_number",
            "display_name": "Chinese mainland mobile number",
            "description": "Detect Chinese mainland mobile phone numbers.",
            "pattern": detector_pattern(CHINA_PHONE_RE),
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 20,
        },
        {
            "rule_id": "cn_id_card",
            "display_name": "Chinese ID card number",
            "description": "Detect 18-digit Chinese ID card numbers.",
            "pattern": detector_pattern(CHINA_ID_RE),
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 30,
        },
        {
            "rule_id": "passport_number",
            "display_name": "Passport number",
            "description": "Detect common passport number formats.",
            "pattern": r"(?i)(?:passport|护照).{0,12}[A-Z0-9]{7,10}\b",
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 40,
        },
        {
            "rule_id": "bank_card_context",
            "display_name": "Bank card context",
            "description": "Detect card-number-like data near bank-card keywords.",
            "pattern": detector_pattern(CARD_CONTEXT_RE),
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 50,
        },
        {
            "rule_id": "personal_address_keywords",
            "display_name": "Personal address keywords",
            "description": "Detect common personal address expressions.",
            "pattern": keyword_pattern(
                "住址", "开户地址", "通信地址", "家庭住址", "收件地址", "mailing address", "home address", "residential address"
            ),
            "severity": RiskSeverity.MEDIUM,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.PERSONAL,
            "sort_order": 60,
        },
        {
            "rule_id": "resume_cv_keywords",
            "display_name": "Resume or CV content",
            "description": "Detect resume and curriculum vitae related content.",
            "pattern": keyword_pattern(
                "简历",
                "履历",
                "resume",
                "curriculum vitae",
                "work experience",
                "employment history",
                "education history",
                "expected salary",
            ),
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
            "pattern": API_KEY_PATTERN,
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 110,
        },
        {
            "rule_id": "credential_assignment",
            "display_name": "Credential assignment pattern",
            "description": "Detect explicit password, secret, token, or API key assignment.",
            "pattern": (
                r"(?i)\b(?P<key>password|passwd|pwd|secret|api[_-]?key|token|client[_-]?secret|access[_-]?key)\b"
                + ASSIGNMENT_OPERATOR
                + ASSIGNED_VALUE
            ),
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 120,
        },
        {
            "rule_id": "jwt_token_like",
            "display_name": "JWT token",
            "description": "Detect JWT-like bearer tokens.",
            "pattern": r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 130,
        },
        {
            "rule_id": "cookie_session_like",
            "display_name": "Session or access token",
            "description": "Detect session IDs, access or refresh tokens, and authorization headers that carry a value.",
            "pattern": (
                r"(?i)\b(?P<key>\w*sessionid|refresh_token|access_token|authorization)\b"
                + ASSIGNMENT_OPERATOR
                + r"(?:(?:bearer|basic|token)\s+)?"
                + ASSIGNED_VALUE
            ),
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 140,
        },
        {
            "rule_id": "db_connection_string",
            "display_name": "Database or queue connection string",
            "description": "Detect connection strings for databases, caches, and queues that embed a password.",
            "pattern": r"(?i)\b(?:mysql|postgres(?:ql)?|mongodb(?:\+srv)?|redis|rediss|amqps?|kafka)://[^\s:@/]*:[^\s@/]+@\S+",
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
            "description": "Detect secret variables such as SECRET_KEY that are set to a value in env-style content.",
            "pattern": (
                r"(?i)\b(?P<key>SECRET_KEY|PRIVATE_KEY|ACCESS_KEY|API_SECRET|CLIENT_SECRET|WEBHOOK_SECRET)\b"
                + ASSIGNMENT_OPERATOR
                + ASSIGNED_VALUE
            ),
            "severity": RiskSeverity.HIGH,
            "action": RiskAction.BLOCK,
            "category": RiskCategory.SECURITY,
            "sort_order": 170,
        },
    ]
    return [*personal_and_security, *BUSINESS_RULES]
