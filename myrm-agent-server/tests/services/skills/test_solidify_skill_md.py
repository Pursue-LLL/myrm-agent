"""The solidified SKILL.md must stay loadable when the artifact title or the user-written fields hold YAML syntax."""

import yaml
from myrm_agent_harness.api.skills import parse_skill_frontmatter

from app.services.skills.solidify import SkillSolidifyService, SolidifySkillRequest
from app.services.skills.solidify.solidify_types import ParameterExtractionRule

_ARTIFACT = '<html><head><title>Quarterly "review": Q3 #1</title></head><body><h1>Quarterly review</h1></body></html>'


def _frontmatter_mapping(skill_md: str) -> dict[str, object]:
    return yaml.safe_load(skill_md.split("---\n")[1])


def test_title_derived_default_with_quotes_and_colon_round_trips() -> None:
    service = SkillSolidifyService()
    request = SolidifySkillRequest(
        name="quarterly-review",
        display_title="Quarterly review",
        description="Build a review deck: summary first",
        source_artifact_content=_ARTIFACT,
    )

    bundle = service.build_skill_bundle(request, service.extract_minimal_parameters(_ARTIFACT, "html"))

    frontmatter = parse_skill_frontmatter(bundle.skill_md_content, "quarterly-review")
    assert frontmatter.description == "Build a review deck: summary first"
    parameters = _frontmatter_mapping(bundle.skill_md_content)["parameters"]
    assert parameters == [
        {
            "name": "topic",
            "description": "Courseware or page core topic/title",
            "required": True,
            "default": 'Quarterly "review": Q3 #1',
        }
    ]


def test_user_written_fields_with_yaml_syntax_stay_plain_text() -> None:
    service = SkillSolidifyService()
    request = SolidifySkillRequest(
        name="deck: v2",
        display_title="Deck # one",
        description="- not a list",
        category="a: b",
        source_artifact_content="<p>{{topic}}</p>",
        custom_parameters=[
            ParameterExtractionRule(
                name="topic",
                description="What the deck covers: scope # not a comment",
                default_value=None,
                placeholder_pattern="{{topic}}",
            )
        ],
    )

    bundle = service.build_skill_bundle(request, request.custom_parameters or [])

    mapping = _frontmatter_mapping(bundle.skill_md_content)
    assert mapping["name"] == "deck: v2"
    assert mapping["display_title"] == "Deck # one"
    assert mapping["description"] == "- not a list"
    assert mapping["category"] == "a: b"
    assert mapping["parameters"] == [
        {"name": "topic", "description": "What the deck covers: scope # not a comment", "required": True, "default": None}
    ]
