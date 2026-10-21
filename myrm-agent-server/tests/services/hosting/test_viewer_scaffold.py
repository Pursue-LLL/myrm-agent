from __future__ import annotations

from app.services.hosting.packager import PublishFile
from app.services.hosting.preflight import evaluate_deploy_preflight
from app.services.hosting.viewer_scaffold import (
    can_scaffold_viewer,
    ensure_viewer_wrapper_for_payload,
    render_standalone_viewer_html,
)


def test_can_scaffold_viewer_for_single_document() -> None:
    pdf_payload = {
        "report.pdf": PublishFile(path="report.pdf", content="JVBERi0xLjQK...", encoding="base64"),
    }
    assert can_scaffold_viewer(pdf_payload) is True

    excel_payload = {
        "data.xlsx": PublishFile(path="data.xlsx", content="UEsDBBQAA...", encoding="base64"),
    }
    assert can_scaffold_viewer(excel_payload) is True

    md_payload = {
        "notes.md": PublishFile(path="notes.md", content="# Notes\nContent", encoding="utf-8"),
    }
    assert can_scaffold_viewer(md_payload) is True


def test_can_scaffold_viewer_rejects_html_or_unsupported() -> None:
    html_payload = {
        "index.html": PublishFile(path="index.html", content="<h1>Hi</h1>", encoding="utf-8"),
    }
    assert can_scaffold_viewer(html_payload) is False

    unsupported_payload = {
        "binary.bin": PublishFile(path="binary.bin", content="AAAA", encoding="base64"),
    }
    assert can_scaffold_viewer(unsupported_payload) is False


def test_render_standalone_viewer_html_embeddable() -> None:
    html_out = render_standalone_viewer_html("report.pdf", title="Annual Report")
    assert "<title>Annual Report</title>" in html_out
    assert 'class="viewer-frame"' in html_out
    assert 'src="./report.pdf"' in html_out
    assert 'href="./report.pdf" download' in html_out


def test_render_standalone_viewer_html_office_card() -> None:
    html_out = render_standalone_viewer_html("financials.xlsx", title="Q3 Financials")
    assert "<title>Q3 Financials</title>" in html_out
    assert 'class="doc-card"' in html_out
    assert "Download XLSX File" in html_out


def test_ensure_viewer_wrapper_for_payload_injects_index_html() -> None:
    pdf_payload = {
        "report.pdf": PublishFile(path="report.pdf", content="JVBERi0xLjQK...", encoding="base64"),
    }
    wrapped = ensure_viewer_wrapper_for_payload(pdf_payload, title="Annual Report")
    assert "index.html" in wrapped
    assert "report.pdf" in wrapped
    assert wrapped["index.html"].encoding == "utf-8"
    assert "<title>Annual Report</title>" in wrapped["index.html"].content


def test_preflight_allows_scaffoldable_artifact() -> None:
    pdf_payload = {
        "report.pdf": PublishFile(path="report.pdf", content="JVBERi0xLjQK...", encoding="base64"),
    }
    result = evaluate_deploy_preflight(pdf_payload)
    assert result.deployable is True
    assert result.reason == "OK"
