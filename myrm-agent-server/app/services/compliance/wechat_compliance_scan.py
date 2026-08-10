"""WeChat Official Account draft compliance scanning (business layer).

Deterministic scan for ad-law superlatives, WeChat inducement phrases, promised
returns, and medical-efficacy claims before HITL draft publish.

[INPUT]
- Draft title, digest, and HTML body content submitted via the WeChat channel
  publish flow (POS: HITL draft publish gate).

[OUTPUT]
- ComplianceCategoryHit: One matched policy category
- ComplianceScanResult: Aggregated scan outcome
- extract_visible_text_from_html: Strip HTML to visible text for scanning
- scan_wechat_draft_content: Scan plain text
- format_compliance_report: Locale-aware report for API/UI
- compliance_hits_payload: Structured hits for 422 responses and draft success warnings
- WeChatComplianceBlockedError: Raised when high-risk hits block publish
- assert_wechat_draft_compliance_html: Scan draft HTML visible text and enforce
- assert_wechat_draft_compliance_for_publish: Scan title, digest, and HTML visible text

[POS]
Business-layer deterministic compliance gate before HITL publish; pure rule
scanning with no LLM calls, keeping regulatory checks offline and predictable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

_HIGH_RISK_CATEGORIES = frozenset({"ad_law_superlative", "wechat_inducement", "promised_returns"})

_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "ad_law_superlative",
        "Advertising superlative terms",
        re.compile(
            "最佳|最好|最优|最强|最高级|最便宜|最先进|最顶级|第一品牌|全国第一|全球第一"
            "|唯一|独家|首个|首选|冠军|领导品牌|国家级|世界级|国际级|顶级|极致"
            "|100%|百分百|绝对|彻底根治|永久|包治|一劳永逸"
        ),
    ),
    (
        "wechat_inducement",
        "WeChat inducement / share-to-unlock",
        re.compile(
            "集赞|助力|砍一刀|分享到朋友圈|分享后解锁|分享解锁|分享可见|转发抽奖|转发领取"
            "|不转不是|关注才能看|关注才可见|关注领取|关注解锁|扫码加个人微信|加我微信领"
        ),
    ),
    (
        "promised_returns",
        "Promised returns or guaranteed outcomes",
        re.compile(
            "保本|稳赚|稳赚不赔|保收益|保底收益|包赚|躺赚|一夜暴富"
            "|包过|保过|保分|名校保录|包录取|包就业|包瘦身"
        ),
    ),
    (
        "medical_efficacy",
        "Medical efficacy claims",
        re.compile("治愈|根治|抗癌|防癌|包瘦|排毒|壮阳|丰胸|生发防脱|药到病除|无副作用"),
    ),
)

_CATEGORY_LABELS_ZH: dict[str, str] = {
    "ad_law_superlative": "广告法极限词",
    "wechat_inducement": "微信诱导",
    "promised_returns": "承诺收益/效果",
    "medical_efficacy": "医疗功效",
}

_CATEGORY_LABELS_EN: dict[str, str] = {
    "ad_law_superlative": "Advertising superlatives",
    "wechat_inducement": "WeChat inducement",
    "promised_returns": "Promised returns",
    "medical_efficacy": "Medical efficacy claims",
}

_SKIP_TAG_RE = re.compile(r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1>")
_SKIP_CONTENT_TAGS = frozenset({"script", "style", "noscript", "pre", "code"})


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _SKIP_CONTENT_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _SKIP_CONTENT_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        stripped = data.strip()
        if stripped:
            self._pieces.append(stripped)

    @property
    def text(self) -> str:
        return "\n".join(self._pieces)


@dataclass(frozen=True, slots=True)
class ComplianceCategoryHit:
    category: str
    label_zh: str
    terms: tuple[str, ...]
    high_risk: bool


@dataclass(frozen=True, slots=True)
class ComplianceScanResult:
    hits: tuple[ComplianceCategoryHit, ...]

    @property
    def clean(self) -> bool:
        return not self.hits

    @property
    def has_high_risk(self) -> bool:
        return any(hit.high_risk for hit in self.hits)


class WeChatComplianceBlockedError(ValueError):
    """Raised when high-risk compliance hits block draft publish."""

    def __init__(self, result: ComplianceScanResult, *, locale: str = "zh") -> None:
        self.result = result
        self.locale = locale
        super().__init__(format_compliance_report(result, locale=locale))


def extract_visible_text_from_html(html: str) -> str:
    """Return visible text from draft HTML, excluding script/style/pre/code blocks."""
    if not html.strip():
        return ""
    stripped = _SKIP_TAG_RE.sub(" ", html)
    parser = _VisibleTextParser()
    parser.feed(stripped)
    parser.close()
    return parser.text


def _resolve_locale(locale: str | None) -> str:
    if not locale:
        return "zh"
    normalized = locale.lower().strip()
    if normalized.startswith("zh"):
        return "zh"
    return "en"


def _category_label(category: str, *, locale: str) -> str:
    if locale == "zh":
        return _CATEGORY_LABELS_ZH[category]
    return _CATEGORY_LABELS_EN[category]


def scan_wechat_draft_content(text: str) -> ComplianceScanResult:
    """Scan draft-bound plain text for compliance violations."""
    if not text.strip():
        return ComplianceScanResult(hits=())

    hits: list[ComplianceCategoryHit] = []
    for category, _label_en, pattern in _RULES:
        found: list[str] = []
        for match in pattern.finditer(text):
            term = match.group(0)
            if term not in found:
                found.append(term)
        if not found:
            continue
        hits.append(
            ComplianceCategoryHit(
                category=category,
                label_zh=_CATEGORY_LABELS_ZH[category],
                terms=tuple(found),
                high_risk=category in _HIGH_RISK_CATEGORIES,
            )
        )
    return ComplianceScanResult(hits=tuple(hits))


def format_compliance_report(result: ComplianceScanResult, *, locale: str = "zh") -> str:
    """Render a locale-aware scan report for UI display."""
    resolved = _resolve_locale(locale)
    if result.clean:
        if resolved == "zh":
            return "合规扫描通过：未检测到需拦截的用词。"
        return "Compliance scan passed: no blocked terms detected."

    if resolved == "zh":
        lines = ["合规扫描发现以下问题："]
        for hit in result.hits:
            severity = "高危" if hit.high_risk else "提示"
            terms = "、".join(hit.terms)
            lines.append(f"- [{hit.label_zh} · {severity}] {terms}")
        if result.has_high_risk:
            lines.append("含高危词，请修改后再推送到公众号草稿。")
        else:
            lines.append("建议修改后再发布。")
        return "\n".join(lines)

    lines = ["Compliance scan found issues:"]
    for hit in result.hits:
        severity = "high risk" if hit.high_risk else "warning"
        label = _category_label(hit.category, locale="en")
        terms = ", ".join(hit.terms)
        lines.append(f"- [{label} · {severity}] {terms}")
    if result.has_high_risk:
        lines.append("High-risk terms must be replaced before pushing to WeChat draft.")
    else:
        lines.append("Review warnings before publishing.")
    return "\n".join(lines)


def compliance_hits_payload(result: ComplianceScanResult, *, locale: str = "zh") -> list[dict[str, object]]:
    """Serialize scan hits for structured API responses."""
    resolved = _resolve_locale(locale)
    payload: list[dict[str, object]] = []
    for hit in result.hits:
        payload.append(
            {
                "category": hit.category,
                "label": _category_label(hit.category, locale=resolved),
                "terms": list(hit.terms),
                "highRisk": hit.high_risk,
            }
        )
    return payload


def assert_wechat_draft_compliance(text: str, *, locale: str = "zh") -> ComplianceScanResult:
    """Scan plain text and raise when high-risk hits would block draft publish."""
    result = scan_wechat_draft_content(text)
    if result.has_high_risk:
        raise WeChatComplianceBlockedError(result, locale=locale)
    return result


def assert_wechat_draft_compliance_html(html: str, *, locale: str = "zh") -> ComplianceScanResult:
    """Scan visible draft HTML text and raise when high-risk hits block publish."""
    visible_text = extract_visible_text_from_html(html)
    result = scan_wechat_draft_content(visible_text)
    if result.has_high_risk:
        raise WeChatComplianceBlockedError(result, locale=locale)
    return result


def assert_wechat_draft_compliance_for_publish(
    html: str,
    *,
    title: str,
    digest: str = "",
    locale: str = "zh",
) -> ComplianceScanResult:
    """Scan draft title, digest, and visible HTML text; raise on high-risk hits."""
    scan_parts: list[str] = []
    stripped_title = title.strip()
    if stripped_title:
        scan_parts.append(stripped_title)
    stripped_digest = digest.strip()
    if stripped_digest:
        scan_parts.append(stripped_digest)
    visible_text = extract_visible_text_from_html(html)
    if visible_text:
        scan_parts.append(visible_text)
    scan_text = "\n".join(scan_parts)
    return assert_wechat_draft_compliance(scan_text, locale=locale)
