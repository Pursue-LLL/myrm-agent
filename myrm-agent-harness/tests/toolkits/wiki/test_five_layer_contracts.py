"""Unit tests for Five-Layer Wiki structure and SourceCardContract."""

import tempfile

from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import (
    WikiPageType,
)
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure


def test_five_layer_wiki_structure_ensure_directories():
    with tempfile.TemporaryDirectory() as tmpdir:
        structure = WikiStructure(base_dir=tmpdir)
        structure.ensure_structure()

        assert structure.raw_dir.is_dir()
        assert structure.sources_dir.is_dir()
        assert structure.wiki_dir.is_dir()
        assert structure.concepts_dir.is_dir()
        assert structure.claims_dir.is_dir()
        assert structure.methods_dir.is_dir()
        assert structure.templates_dir.is_dir()
        assert structure.deliverables_dir.is_dir()
        assert structure.inbox_dir.is_dir()
        assert structure.archive_dir.is_dir()

        # Path getters
        src_path = structure.get_source_file_path("src_paper_2026")
        assert src_path.parent == structure.sources_dir
        assert src_path.name == "src-paper-2026.md"

        deliv_path = structure.get_deliverable_file_path("bank_proposal.md")
        assert deliv_path.parent == structure.deliverables_dir

        claim_path = structure.get_claim_file_path("author_viewpoint")
        assert claim_path.parent == structure.claims_dir


def test_frontmatter_page_types_extended():
    assert WikiPageType.CLAIM == "claim"
    assert WikiPageType.METHOD == "method"
    assert WikiPageType.TEMPLATE == "template"
    assert WikiPageType.DELIVERABLE == "deliverable"
