"""[INPUT] SolidifySkillRequest and ExternalPreviewCreateRequest schemas.
[OUTPUT] SkillSolidifyService orchestrating parameter minimization, 4-in-1 asset bundle creation, and clean browser preview.
[POS] app/services/skills/solidify/skill_solidify_service.py.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.core.skills.utils import yaml_scalar

from .solidify_types import (
    ExternalPreviewCreateRequest,
    ExternalPreviewMetadata,
    ParameterExtractionRule,
    SkillAssetBundle,
    SolidifySkillRequest,
    SolidifySkillResponse,
)


class SkillSolidifyService:
    """Service implementing 1-click artifact solidification to 4-in-1 skill bundle & clean preview."""

    _instance: Optional["SkillSolidifyService"] = None

    def __init__(self) -> None:
        self._preview_cache: Dict[str, Tuple[str, str]] = {}
        self._preview_meta: Dict[str, ExternalPreviewMetadata] = {}
        self._skills_registry: Dict[str, Tuple[SolidifySkillResponse, SkillAssetBundle]] = {}

    @classmethod
    def get_instance(cls) -> "SkillSolidifyService":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset instance for isolated unit testing."""
        cls._instance = None

    def extract_minimal_parameters(self, source_content: str, source_type: str = "html") -> List[ParameterExtractionRule]:
        """Automatically identify dynamic parameter slots adhering to parameter minimization principles."""
        extracted: List[ParameterExtractionRule] = []
        found_keys: set[str] = set()

        # 1. Match explicit template expressions like {{param}} or ${param}
        explicit_patterns = re.findall(r"\{\{([a-zA-Z0-9_\u4e00-\u9fa5]+)\}\}", source_content)
        for key in explicit_patterns:
            clean_key = key.strip()
            if clean_key and clean_key not in found_keys:
                found_keys.add(clean_key)
                extracted.append(
                    ParameterExtractionRule(
                        name=clean_key,
                        description=f"Dynamic content slot for {clean_key}",
                        default_value=None,
                        placeholder_pattern=f"{{{{{clean_key}}}}}",
                        required=True,
                    )
                )

        if extracted:
            return extracted

        # 2. Heuristic extraction for raw HTML deliverables
        if source_type.lower() == "html":
            title_match = re.search(r"<title>(.*?)</title>", source_content, re.IGNORECASE | re.DOTALL)
            if title_match:
                title_val = title_match.group(1).strip()
                if title_val and "topic" not in found_keys:
                    found_keys.add("topic")
                    extracted.append(
                        ParameterExtractionRule(
                            name="topic",
                            description="Courseware or page core topic/title",
                            default_value=title_val,
                            placeholder_pattern="{{topic}}",
                            required=True,
                        )
                    )

            h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", source_content, re.IGNORECASE | re.DOTALL)
            if h1_match:
                h1_val = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
                if h1_val and "headline" not in found_keys and "topic" not in found_keys:
                    found_keys.add("headline")
                    extracted.append(
                        ParameterExtractionRule(
                            name="headline",
                            description="Primary headline or main lesson title",
                            default_value=h1_val,
                            placeholder_pattern="{{headline}}",
                            required=True,
                        )
                    )

        # 3. Default fallback parameter if no matches found
        if not extracted:
            extracted.append(
                ParameterExtractionRule(
                    name="topic",
                    description="Primary subject or theme of the deliverable",
                    default_value="General Subject",
                    placeholder_pattern="{{topic}}",
                    required=True,
                )
            )

        return extracted

    def build_skill_bundle(self, request: SolidifySkillRequest, parameters: List[ParameterExtractionRule]) -> SkillAssetBundle:
        """Build standard 4-in-1 directory bundle: SKILL.md + assets/ + references/."""
        # 1. Prepare example HTML
        example_content = request.source_artifact_content

        # 2. Prepare template HTML by replacing identified slot values with placeholders
        template_content = example_content
        for param in parameters:
            if param.default_value and param.default_value in template_content:
                template_content = template_content.replace(param.default_value, param.placeholder_pattern)

        # 3. Generate structured SKILL.md with YAML frontmatter
        params_yaml_lines: List[str] = []
        for p in parameters:
            req_str = "true" if p.required else "false"
            def_str = yaml_scalar(p.default_value) if p.default_value else "null"
            params_yaml_lines.append(
                f"  - name: {yaml_scalar(p.name)}\n    description: {yaml_scalar(p.description)}\n"
                f"    required: {req_str}\n    default: {def_str}"
            )
        params_yaml_block = "\n".join(params_yaml_lines) if params_yaml_lines else "  []"

        plan_directive = (
            "\n### Execution Phase Rule\n"
            "1. **Plan First**: Always present a structured layout wireframe and plan before streaming the final code.\n"
            "2. **Acknowledge User Choices**: Ensure all pre-flight preference selections are respected."
            if request.include_plan_before_execute_hint
            else ""
        )

        skill_md = (
            f"---\n"
            f"name: {yaml_scalar(request.name)}\n"
            f"display_title: {yaml_scalar(request.display_title)}\n"
            f"description: {yaml_scalar(request.description)}\n"
            f"category: {yaml_scalar(request.category)}\n"
            f"parameters:\n{params_yaml_block}\n"
            f"---\n\n"
            f"# {request.display_title}\n\n"
            f"{request.description}\n\n"
            f"## Operating Principles (Adhering to Parameter Minimization)\n"
            f"- **Immutable Skeleton**: Only variable data points ({', '.join(p.name for p in parameters)}) should be dynamically replaced.\n"
            f"- **Asset Integrity**: Keep CSS styling and responsive layouts intact as standardized in `assets/template.html`.\n"
            f"{plan_directive}\n\n"
            f"## Usage Guidelines\n"
            f"When invoked with user parameters, load `assets/template.html`, replace all corresponding `{{...}}` slots, and return single-file clean deliverable.\n"
        )

        ref_md = (
            f"# Reference Design Guidelines for {request.display_title}\n\n"
            f"- Responsive viewport breakpoint: desktop 1280px, tablet 768px, mobile 375px.\n"
            f"- Zero inline broken images: use standardized vector SVGs or safe data URIs.\n"
        )

        paths = [
            "SKILL.md",
            "assets/example.html",
            "assets/template.html",
            "references/design_guidelines.md",
        ]

        return SkillAssetBundle(
            skill_md_content=skill_md,
            template_content=template_content,
            example_content=example_content,
            reference_md_content=ref_md,
            relative_paths=paths,
        )

    def solidify_skill(self, request: SolidifySkillRequest) -> SolidifySkillResponse:
        """Solidify artifact into full reusable skill."""
        skill_id = f"skill-{uuid.uuid4().hex[:12]}"

        # Select dynamic parameters
        parameters = (
            request.custom_parameters
            if request.custom_parameters and len(request.custom_parameters) > 0
            else self.extract_minimal_parameters(request.source_artifact_content, request.source_artifact_type)
        )

        # Generate bundle
        bundle = self.build_skill_bundle(request, parameters)

        # Register preview for immediate testing
        preview_meta = self.register_clean_preview(
            ExternalPreviewCreateRequest(
                content=request.source_artifact_content,
                content_type="text/html",
                title=f"{request.display_title} - Preview",
            )
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        response = SolidifySkillResponse(
            skill_id=skill_id,
            name=request.name,
            display_title=request.display_title,
            description=request.description,
            parameters=parameters,
            bundle_files=bundle.relative_paths,
            preview_url=preview_meta.view_url,
            created_at=now_iso,
        )

        self._skills_registry[skill_id] = (response, bundle)
        return response

    def get_skill_bundle(self, skill_id: str) -> Optional[SkillAssetBundle]:
        """Fetch generated bundle for a solidified skill."""
        record = self._skills_registry.get(skill_id)
        if not record:
            return None
        return record[1]

    def register_clean_preview(self, request: ExternalPreviewCreateRequest) -> ExternalPreviewMetadata:
        """Register standalone clean preview page to bypass iframe CSP & referrer issues."""
        preview_id = f"prev-{uuid.uuid4().hex[:16]}"
        self._preview_cache[preview_id] = (request.content, request.content_type)

        meta = ExternalPreviewMetadata(
            preview_id=preview_id,
            title=request.title,
            content_type=request.content_type,
            view_url=f"/api/v1/skills/solidify/preview/{preview_id}",
        )
        self._preview_meta[preview_id] = meta
        return meta

    def get_clean_preview(self, preview_id: str) -> Optional[Tuple[str, str, str]]:
        """Fetch raw preview content, content_type, and title."""
        if preview_id not in self._preview_cache:
            return None
        content, content_type = self._preview_cache[preview_id]
        meta = self._preview_meta.get(preview_id)
        title = meta.title if meta else "Clean Preview"
        return content, content_type, title
