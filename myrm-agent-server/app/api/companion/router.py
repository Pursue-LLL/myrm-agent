"""Companion API — Observer reactions, evolution status, companion config, and the Petdex pet routes.

[INPUT]
app.api.companion.pets.router (POS: Petdex 宠物的安装 / 列表 / 精灵图 / 卸载端点，挂在本路由下共用 feature gate)
app.api.companion.pets.sprite_selection (POS: 伴侣配置里的精灵选择，旧配置迁移时写入)
app.api.dependencies::get_deploy_identity (POS: 全局依赖注入)
app.core.channel_bridge.config_loader (POS: 用户模型配置加载)
app.core.utils.chat_utils::extract_answer_text (POS: LangChain 响应文本提取，含 reasoning 回退)
app.database.connection::get_db (POS: 数据库会话工厂)
app.database.models::Chat, Message (POS: 数据库 ORM 模型)
app.database.models.chat::NOT_WAKEUP_NOTICE (POS: 排除后台完成通知行，活跃度只数用户亲自发的消息)
app.schemas.config::ConfigRecord (POS: 配置记录，含 value 与 version)
app.services.companion.pet_store (POS: on-disk Petdex install store)

[OUTPUT]
router: FastAPI APIRouter with companion endpoints

[POS]
Companion API 端点。Observer 生成宠物反应，Evolution 查询用户活跃度指标和进化资格，
伴侣配置读写；Petdex 宠物端点由 pets 子包提供并挂在这里，共用 `companion_mode` feature gate。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.companion.pets.router import router as pets_router
from app.api.companion.pets.sprite_selection import persist_sprite_selection
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import extract_lite_model_config
from app.core.utils.chat_utils import extract_answer_text
from app.database.connection import get_db
from app.database.models import Chat, Message
from app.database.models.chat import NOT_WAKEUP_NOTICE
from app.schemas.config import ConfigRecord
from app.services.agent.platform_config import load_llm_from_model_config

logger = logging.getLogger(__name__)


def verify_companion_enabled() -> None:
    from myrm_agent_harness.core.features import get_features

    feature_set = get_features()
    if not feature_set.enabled("companion_mode"):
        raise HTTPException(status_code=403, detail="Companion feature is disabled via Feature Gate")


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

    model_kwargs = dict(model_cfg.model_kwargs or {})
    model_kwargs["max_tokens"] = _MAX_REACTION_TOKENS
    # A reaction this short must not be lifted to a thinking model's output floor.
    model_kwargs["supports_reasoning"] = False
    invoke_cfg = model_cfg.model_copy(
        update={"temperature": 0.9, "model_kwargs": model_kwargs},
    )

    try:
        llm = await load_llm_from_model_config(invoke_cfg, streaming=False)
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_msg),
                HumanMessage(content=f"Assistant said: {req.snippet}"),
            ],
        )
        text = extract_answer_text(response).strip().strip('"').strip("'")
        reaction = text.strip()
        if not reaction:
            raise HTTPException(status_code=204, detail="Empty reaction")
        return CompanionReactResponse(reaction=reaction[:100])
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("companion_observer_failed: %s", exc)
        raise HTTPException(status_code=502, detail="Companion reaction generation failed") from exc


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
    active_days_q = select(func.count(func.distinct(func.date(Message.created_at)))).where(
        and_(
            Message.chat_id.in_(select(user_chats.c.id)),
            Message.role == "user",
            NOT_WAKEUP_NOTICE,
        )
    )
    total_messages_q = select(func.count(Message.id)).where(
        and_(
            Message.chat_id.in_(select(user_chats.c.id)),
            Message.role == "user",
            NOT_WAKEUP_NOTICE,
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
        if conversations >= req_conv and active_days >= req_days and total_messages >= req_msgs:
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


class SpriteConfigValue(BaseModel):
    pet_slug: str
    content_sha256: str | None = None
    display_name: str | None = None


class CompanionConfigValue(BaseModel):
    name: str | None = None
    species: str | None = None
    hat: str | None = None
    sprite: SpriteConfigValue | None = None


class CompanionConfigResponse(BaseModel):
    value: CompanionConfigValue
    version: str | None = None


class CompanionConfigSetRequest(BaseModel):
    value: CompanionConfigValue
    device_id: str = "default_device"


def _sprite_from_raw(raw: object) -> SpriteConfigValue | None:
    if not isinstance(raw, dict):
        return None
    pet_slug = raw.get("pet_slug")
    if isinstance(pet_slug, str) and pet_slug.strip():
        sha = raw.get("content_sha256")
        display_name = raw.get("display_name")
        return SpriteConfigValue(
            pet_slug=pet_slug.strip(),
            content_sha256=sha if isinstance(sha, str) and sha else None,
            display_name=(display_name if isinstance(display_name, str) and display_name else None),
        )
    return None


def _companion_value_from_record(val: dict[str, object]) -> CompanionConfigValue:
    name, species, hat = val.get("name"), val.get("species"), val.get("hat")
    return CompanionConfigValue(
        name=name if isinstance(name, str) else None,
        species=species if isinstance(species, str) else None,
        hat=hat if isinstance(hat, str) else None,
        sprite=_sprite_from_raw(val.get("sprite")),
    )


def _config_response(record: ConfigRecord) -> CompanionConfigResponse:
    return CompanionConfigResponse(value=_companion_value_from_record(record.value), version=record.version)


@router.get("/config", response_model=CompanionConfigResponse)
async def get_companion_config() -> CompanionConfigResponse:
    """Get the persisted companion customization config."""
    from app.services.config.service import config_service

    record = await config_service.get("companion_config")
    if not record:
        return CompanionConfigResponse(value=CompanionConfigValue())

    val = record.value if isinstance(record.value, dict) else {}
    sprite_raw = val.get("sprite")
    if isinstance(sprite_raw, dict) and sprite_raw.get("sheet_url") and not sprite_raw.get("pet_slug"):
        legacy_slug = sprite_raw.get("name")
        if isinstance(legacy_slug, str) and legacy_slug.strip():
            try:
                from app.services.companion.pet_store import PetStoreError, install_pet

                installed = await install_pet(legacy_slug.strip())
                migrated = await persist_sprite_selection(
                    pet_slug=installed.slug,
                    content_sha256=installed.content_sha256,
                    display_name=installed.display_name,
                )
                return _config_response(migrated)
            except PetStoreError as exc:
                logger.warning("Legacy companion sprite migration failed: %s", exc)
                cleaned = dict(val)
                cleaned["sprite"] = None
                saved = await config_service.set(
                    config_key="companion_config",
                    value=cleaned,
                    device_id="default_device",
                )
                return _config_response(saved)

    return CompanionConfigResponse(value=_companion_value_from_record(val), version=record.version)


@router.post("/config", response_model=CompanionConfigResponse)
async def set_companion_config(
    req: CompanionConfigSetRequest,
) -> CompanionConfigResponse:
    """Set and persist the companion customization config."""
    from app.services.config.service import config_service

    sprite_dict: dict[str, object] | None = None
    if req.value.sprite is not None:
        sprite_dict = {
            "pet_slug": req.value.sprite.pet_slug,
            "content_sha256": req.value.sprite.content_sha256,
            "display_name": req.value.sprite.display_name,
        }

    value_dict: dict[str, object] = {
        "name": req.value.name,
        "species": req.value.species,
        "hat": req.value.hat,
        "sprite": sprite_dict,
    }
    record = await config_service.set(
        config_key="companion_config",
        value=value_dict,
        device_id=req.device_id,
    )
    return _config_response(record)


router.include_router(pets_router)
