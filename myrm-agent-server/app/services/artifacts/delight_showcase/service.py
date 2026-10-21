"""[INPUT]
- Harness delight_showcase: SingleFileSandboxEngine, DelightTemplate, DelightCategory, SingleFileSandboxContract, SandboxValidationResult
- catalog: PREBUILT_DELIGHT_TEMPLATES

[OUTPUT]
- DelightShowcaseService: Application service governing prebuilt hobbyist templates and sandbox validation

[POS]
Server service layer for Zero-Code Hobbyist Delight & Single-File Sandbox (Item 40 P0).
Strictly under 160 lines. Zero `Any`.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.toolkits.artifacts.delight_showcase import (
    DelightTemplate,
    SandboxValidationResult,
    SingleFileSandboxContract,
    SingleFileSandboxEngine,
)

from .catalog import PREBUILT_DELIGHT_TEMPLATES


class DelightShowcaseService:
    """Singleton service providing hobbyist delight templates and single-file sandbox validation."""

    _instance: DelightShowcaseService | None = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self._engine = SingleFileSandboxEngine()
        self._templates: list[DelightTemplate] = list(PREBUILT_DELIGHT_TEMPLATES)
        self._contracts: dict[str, SingleFileSandboxContract] = {}

    @classmethod
    def get_instance(cls) -> DelightShowcaseService:
        """Returns the process-wide singleton service instance."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def list_templates(
        self,
        category: str | None = None,
        query: str | None = None,
    ) -> list[DelightTemplate]:
        """Filters delight templates by optional category and search keyword."""
        results = self._templates
        if category and category.lower() != "all":
            results = [t for t in results if t.category == category]

        if query:
            q = query.strip().lower()
            results = [
                t
                for t in results
                if q in t.title.lower() or q in t.description.lower() or any(q in tag.lower() for tag in t.tags)
            ]

        return results

    def get_template(self, template_id: str) -> DelightTemplate | None:
        """Looks up a specific delight template by unique template_id."""
        for tmpl in self._templates:
            if tmpl.template_id == template_id:
                return tmpl
        return None

    def validate_and_compile(
        self,
        html_source: str,
        title: str = "Delight Sandbox",
    ) -> SandboxValidationResult:
        """Inspects HTML code for self-contained single-file compliance and compiles viewport safety."""
        return self._engine.validate_and_compile(html_source, title=title)

    def create_contract(
        self,
        session_id: str,
        title: str,
        html_source: str,
    ) -> SingleFileSandboxContract:
        """Produces and records a verified SingleFileSandboxContract."""
        contract = self._engine.create_contract(session_id, title, html_source)
        self._contracts[contract.contract_id] = contract
        return contract

    def get_contract(self, contract_id: str) -> SingleFileSandboxContract | None:
        """Retrieves a previously created sandbox contract by ID."""
        return self._contracts.get(contract_id)
