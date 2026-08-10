"""Tests for WeChat draft compliance scanning."""

from __future__ import annotations

import pytest

from app.services.compliance.wechat_compliance_scan import (
    WeChatComplianceBlockedError,
    assert_wechat_draft_compliance,
    assert_wechat_draft_compliance_for_publish,
    assert_wechat_draft_compliance_html,
    compliance_hits_payload,
    extract_visible_text_from_html,
    format_compliance_report,
    scan_wechat_draft_content,
)


def test_scan_detects_ad_law_superlative_as_high_risk() -> None:
    result = scan_wechat_draft_content("我们是全国第一、效果最好的品牌")
    assert not result.clean
    assert result.has_high_risk
    assert "广告法极限词" in format_compliance_report(result, locale="zh")


def test_scan_detects_wechat_inducement_as_high_risk() -> None:
    result = scan_wechat_draft_content("集赞 20 个送礼品，分享到朋友圈解锁全文")
    assert result.has_high_risk


def test_scan_medical_efficacy_is_warning_not_block() -> None:
    result = scan_wechat_draft_content("这款茶能排毒养颜")
    assert not result.clean
    assert not result.has_high_risk


def test_assert_blocks_high_risk_copy() -> None:
    with pytest.raises(WeChatComplianceBlockedError):
        assert_wechat_draft_compliance("保本理财，稳赚不赔")


def test_clean_copy_passes() -> None:
    result = assert_wechat_draft_compliance("这是我上周做的三道家常菜，步骤和用量都写清楚了。")
    assert result.clean


def test_extract_visible_text_skips_script_blocks() -> None:
    html = "<html><body><p>正常正文</p><script>保本理财，稳赚不赔</script></body></html>"
    assert extract_visible_text_from_html(html) == "正常正文"
    assert_wechat_draft_compliance_html(html)


def test_extract_visible_text_skips_pre_code_blocks() -> None:
    html = (
        "<html><body><p>正常正文</p>"
        "<pre><code>保本理财，稳赚不赔</code></pre>"
        "</body></html>"
    )
    assert extract_visible_text_from_html(html) == "正常正文"
    assert_wechat_draft_compliance_html(html)


def test_assert_html_blocks_visible_high_risk_terms() -> None:
    html = "<html><body><p>欢迎关注，集赞 20 个送礼品</p></body></html>"
    with pytest.raises(WeChatComplianceBlockedError) as exc_info:
        assert_wechat_draft_compliance_html(html, locale="zh")
    assert "集赞" in str(exc_info.value)


def test_format_compliance_report_uses_chinese_for_zh_locale() -> None:
    result = scan_wechat_draft_content("保本理财，稳赚不赔")
    report = format_compliance_report(result, locale="zh")
    assert "合规扫描发现以下问题" in report
    assert "高危" in report


def test_compliance_hits_payload_serializes_structured_hits() -> None:
    result = scan_wechat_draft_content("保本理财，稳赚不赔")
    payload = compliance_hits_payload(result, locale="zh")
    assert payload
    assert payload[0]["category"] == "promised_returns"
    assert payload[0]["highRisk"] is True
    assert "保本" in payload[0]["terms"]


def test_assert_for_publish_scans_title_with_clean_html() -> None:
    html = "<html><body><p>正常正文</p></body></html>"
    with pytest.raises(WeChatComplianceBlockedError) as exc_info:
        assert_wechat_draft_compliance_for_publish(
            html,
            title="全国第一好茶",
            locale="zh",
        )
    assert "全国第一" in str(exc_info.value)


def test_assert_for_publish_returns_warning_when_title_has_medical_term() -> None:
    html = "<html><body><p>正常正文</p></body></html>"
    result = assert_wechat_draft_compliance_for_publish(
        html,
        title="春季排毒养生指南",
        locale="zh",
    )
    assert not result.clean
    assert not result.has_high_risk
    assert any("排毒" in hit.terms for hit in result.hits)


def test_extract_visible_text_returns_empty_for_blank_html() -> None:
    assert extract_visible_text_from_html("") == ""
    assert extract_visible_text_from_html("   ") == ""


def test_scan_empty_text_is_clean() -> None:
    result = scan_wechat_draft_content("")
    assert result.clean
    assert not result.has_high_risk


def test_format_compliance_report_clean_en_locale() -> None:
    result = scan_wechat_draft_content("正常教程内容")
    report = format_compliance_report(result, locale="en")
    assert "Compliance scan passed" in report


def test_format_compliance_report_high_risk_en_locale() -> None:
    result = scan_wechat_draft_content("保本理财，稳赚不赔")
    report = format_compliance_report(result, locale="en")
    assert "Compliance scan found issues" in report
    assert "High-risk terms must be replaced" in report


def test_format_compliance_report_warning_only_en_locale() -> None:
    result = scan_wechat_draft_content("这款茶能排毒养颜")
    report = format_compliance_report(result, locale="en")
    assert "Review warnings before publishing" in report


def test_compliance_hits_payload_uses_en_labels() -> None:
    result = scan_wechat_draft_content("这款茶能排毒养颜")
    payload = compliance_hits_payload(result, locale="en")
    assert payload[0]["label"] == "Medical efficacy claims"


def test_format_compliance_report_warning_only_zh_locale() -> None:
    result = scan_wechat_draft_content("这款茶能排毒养颜")
    report = format_compliance_report(result, locale="zh")
    assert "建议修改后再发布" in report


def test_compliance_hits_payload_defaults_locale_to_zh() -> None:
    result = scan_wechat_draft_content("这款茶能排毒养颜")
    payload = compliance_hits_payload(result, locale=None)
    assert payload[0]["label"] == "医疗功效"
