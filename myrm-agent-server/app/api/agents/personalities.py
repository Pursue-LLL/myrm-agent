"""Communication style catalog API.

[INPUT]
- app.ai_agents.personality_templates::list_all_personalities (POS: Personality template catalog SSOT)
- app.ai_agents.personality_templates::PersonalityCategory (POS: Catalog category literal)

[OUTPUT]
- get_personality_catalog(): GET /agents/personalities returning the 17 preset communication
  styles with bilingual names, descriptions, examples, and the GUI icon id.

[POS]
Read-only catalog endpoint for the agent editor. The catalog itself lives in
app.ai_agents.personality_templates; this module only serializes it, so the GUI
never keeps a second copy of the style list and a new preset needs no frontend change.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.ai_agents.personality_templates import (
    PersonalityCategory,
    list_all_personalities,
)
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse

router = APIRouter()


class PersonalityCatalogEntryResponse(BaseModel):
    """One communication style preset as shown in the agent editor."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    display_name: str
    display_name_zh: str
    description: str
    description_zh: str
    example_response: str
    example_response_zh: str
    icon_id: str
    category: PersonalityCategory


@router.get("/personalities", response_model=StandardSuccessResponse)
async def get_personality_catalog() -> JSONResponse:
    """List the built-in communication style presets."""
    entries = [
        PersonalityCatalogEntryResponse(
            id=template.name,
            display_name=template.display_name,
            display_name_zh=template.display_name_zh,
            description=template.description,
            description_zh=template.description_zh,
            example_response=template.example_response,
            example_response_zh=template.example_response_zh,
            icon_id=template.icon_id,
            category=template.category,
        ).model_dump(by_alias=True)
        for template in list_all_personalities()
    ]
    return success_response(data=entries)
