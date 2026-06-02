"""Companion API — Observer reactions and evolution status.

[INPUT]
app.api.dependencies::get_deploy_identity (POS: 全局依赖注入)
app.core.channel_bridge.config_loader (POS: 用户模型配置加载)
app.database.connection::get_db (POS: 数据库会话工厂)
app.database.models::Chat, Message (POS: 数据库 ORM 模型)

[OUTPUT]
router: FastAPI APIRouter with POST /react and GET /evolution-status

[POS]
Companion API 端点。Observer 生成宠物反应，Evolution 查询用户活跃度指标和进化资格。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import extract_lite_model_config
from app.database.connection import get_db
from app.database.models import Chat, Message

logger = logging.getLogger(__name__)


def verify_companion_enabled() -> None:
    from myrm_agent_harness.core.features import get_features

    feature_set = get_features()
    if not feature_set.enabled("companion_mode"):
        raise HTTPException(
            status_code=403, detail="Companion feature is disabled via Feature Gate"
        )


router = APIRouter(dependencies=[Depends(verify_companion_enabled)])

_MAX_REACTION_TOKENS = 30
_OBSERVER_SYSTEM_PROMPT = (
    "You are {name}, a tiny {species} companion. "
    "Personality: {personality}. "
    "React to the assistant's last message in ≤10 words. "
    "Be brief, cute, in-character. No quotes, no emojis."
)

# Evolution thresholds: (conversations, active_days, total_messages)
_EVOLUTION_THRESHOLDS: dict[str, tuple[int, int, int]] = {
    "Uncommon": (10, 7, 50),
    "Rare": (30, 21, 150),
    "Epic": (60, 45, 400),
    "Legendary": (120, 90, 1000),
}

_RARITY_ORDER = ("Common", "Uncommon", "Rare", "Epic", "Legendary")


class CompanionReactRequest(BaseModel):
    snippet: str = Field(..., min_length=1, max_length=500)
    personality: str = Field(..., max_length=200)
    name: str = Field(..., max_length=50)
    species: str = Field(..., max_length=10)
    isBirthday: bool = False


class CompanionReactResponse(BaseModel):
    reaction: str


@router.post("/react", response_model=CompanionReactResponse)
async def companion_react(
    req: CompanionReactRequest,
) -> CompanionReactResponse:
    """Generate a short pet reaction to the last assistant message."""
    configs = await load_user_configs()
    providers_dict = configs.providers_dict

    if not providers_dict:
        raise HTTPException(status_code=422, detail="No model configured")

    filter_cfg = extract_lite_model_config(providers_dict)
    model_cfg = filter_cfg or configs.model_cfg

    system_msg = _OBSERVER_SYSTEM_PROMPT.format(
        name=req.name,
        species=req.species,
        personality=req.personality,
    )
    if req.isBirthday:
        system_msg += " Today is your birthday — you're extra excited!"

    try:
        import litellm

        response = await litellm.acompletion(
            model=model_cfg.model,
            api_key=model_cfg.api_key,
            base_url=model_cfg.base_url,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Assistant said: {req.snippet}"},
            ],
            max_tokens=_MAX_REACTION_TOKENS,
            temperature=0.9,
        )
        text = response.choices[0].message.content or ""
        reaction = text.strip().strip('"').strip("'")
        if not reaction:
            raise HTTPException(status_code=204, detail="Empty reaction")
        return CompanionReactResponse(reaction=reaction[:100])
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("companion_observer_failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Companion reaction generation failed"
        ) from exc


# ---------------------------------------------------------------------------
# Evolution status
# ---------------------------------------------------------------------------


class EvolutionMetrics(BaseModel):
    conversations: int
    active_days: int
    total_messages: int


class EvolutionThreshold(BaseModel):
    conversations: int
    active_days: int
    total_messages: int


class EvolutionStatusResponse(BaseModel):
    metrics: EvolutionMetrics
    current_rarity: str
    max_reachable_rarity: str
    can_evolve: bool
    next_threshold: EvolutionThreshold | None


@router.get("/evolution-status", response_model=EvolutionStatusResponse)
async def get_evolution_status(
    current_rarity: str = "Common",
    db: AsyncSession = Depends(get_db),
) -> EvolutionStatusResponse:
    """Return user activity metrics and evolution eligibility."""
    if current_rarity not in _RARITY_ORDER:
        raise HTTPException(status_code=400, detail=f"Invalid rarity: {current_rarity}")

    user_chats = select(Chat.id).subquery()

    conversations_q = select(func.count()).select_from(user_chats)
    active_days_q = select(
        func.count(func.distinct(func.date(Message.created_at)))
    ).where(
        and_(
            Message.chat_id.in_(select(user_chats.c.id)),
            Message.role == "user",
        )
    )
    total_messages_q = select(func.count(Message.id)).where(
        and_(
            Message.chat_id.in_(select(user_chats.c.id)),
            Message.role == "user",
        )
    )

    conversations = (await db.execute(conversations_q)).scalar() or 0
    active_days = (await db.execute(active_days_q)).scalar() or 0
    total_messages = (await db.execute(total_messages_q)).scalar() or 0

    metrics = EvolutionMetrics(
        conversations=conversations,
        active_days=active_days,
        total_messages=total_messages,
    )

    current_idx = _RARITY_ORDER.index(current_rarity)
    max_reachable = current_rarity

    for rarity in _RARITY_ORDER[current_idx + 1 :]:
        req_conv, req_days, req_msgs = _EVOLUTION_THRESHOLDS[rarity]
        if (
            conversations >= req_conv
            and active_days >= req_days
            and total_messages >= req_msgs
        ):
            max_reachable = rarity
        else:
            break

    can_evolve = _RARITY_ORDER.index(max_reachable) > current_idx

    next_threshold: EvolutionThreshold | None = None
    next_idx = _RARITY_ORDER.index(max_reachable) + 1
    if next_idx < len(_RARITY_ORDER):
        next_rarity = _RARITY_ORDER[next_idx]
        req = _EVOLUTION_THRESHOLDS[next_rarity]
        next_threshold = EvolutionThreshold(
            conversations=req[0],
            active_days=req[1],
            total_messages=req[2],
        )

    return EvolutionStatusResponse(
        metrics=metrics,
        current_rarity=current_rarity,
        max_reachable_rarity=max_reachable,
        can_evolve=can_evolve,
        next_threshold=next_threshold,
    )


class CompanionConfigValue(BaseModel):
    name: str | None = None
    species: str | None = None
    hat: str | None = None
    palette_theme: str | None = None


class CompanionConfigResponse(BaseModel):
    value: CompanionConfigValue
    version: str | None = None


class CompanionConfigSetRequest(BaseModel):
    value: CompanionConfigValue
    device_id: str = "default_device"


@router.get("/config", response_model=CompanionConfigResponse)
async def get_companion_config() -> CompanionConfigResponse:
    """Get the persisted companion customization config."""
    from app.services.config.service import config_service

    record = await config_service.get("companion_config")
    if not record:
        return CompanionConfigResponse(value=CompanionConfigValue())

    val = record.value
    return CompanionConfigResponse(
        value=CompanionConfigValue(
            name=val.get("name"),
            species=val.get("species"),
            hat=val.get("hat"),
            palette_theme=val.get("palette_theme"),
        ),
        version=record.version,
    )


@router.post("/config", response_model=CompanionConfigResponse)
async def set_companion_config(
    req: CompanionConfigSetRequest,
) -> CompanionConfigResponse:
    """Set and persist the companion customization config."""
    from app.services.config.service import config_service

    value_dict = {
        "name": req.value.name,
        "species": req.value.species,
        "hat": req.value.hat,
        "palette_theme": req.value.palette_theme,
    }
    record = await config_service.set(
        config_key="companion_config",
        value=value_dict,
        device_id=req.device_id,
    )
    return CompanionConfigResponse(
        value=CompanionConfigValue(
            name=record.value.get("name"),
            species=record.value.get("species"),
            hat=record.value.get("hat"),
            palette_theme=record.value.get("palette_theme"),
        ),
        version=record.version,
    )
