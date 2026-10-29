"""Companion pets API — Petdex install, list, serve and uninstall.

[INPUT]
app.api.companion.pets.sprite_selection (POS: 伴侣配置里的精灵选择，装宠物时写入、卸载当前宠物时清除)
app.services.companion.pet_store (POS: on-disk Petdex install store)

[OUTPUT]
router: FastAPI APIRouter with the `/pets` endpoints (mounted by `app.api.companion.router`, which supplies the feature gate)

[POS]
Petdex 宠物的安装、列表、精灵图下载与卸载端点；安装工件持久化在 MYRM_DATA_DIR/companion/pets/。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.companion.pets.sprite_selection import clear_sprite_selection_if_matches, persist_sprite_selection

router = APIRouter()


class PetInstallRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120)
    force: bool = False


class InstalledPetResponse(BaseModel):
    slug: str
    display_name: str
    content_sha256: str
    format_label: str | None = None
    format_tier: str | None = None


class InstalledPetListResponse(BaseModel):
    pets: list[InstalledPetResponse]


@router.get("/pets", response_model=InstalledPetListResponse)
async def list_installed_pets() -> InstalledPetListResponse:
    from app.services.companion.pet_store import list_installed_pets

    pets = [
        InstalledPetResponse(
            slug=pet.slug,
            display_name=pet.display_name,
            content_sha256=pet.content_sha256,
            format_label=pet.format_label,
            format_tier=pet.format_tier,
        )
        for pet in list_installed_pets()
    ]
    return InstalledPetListResponse(pets=pets)


@router.post("/pets/install", response_model=InstalledPetResponse)
async def install_companion_pet(req: PetInstallRequest) -> InstalledPetResponse:
    from app.services.companion.pet_store import PetStoreError, install_pet

    try:
        installed = await install_pet(req.slug, force=req.force)
    except PetStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await persist_sprite_selection(
        pet_slug=installed.slug,
        content_sha256=installed.content_sha256,
        display_name=installed.display_name,
    )
    return InstalledPetResponse(
        slug=installed.slug,
        display_name=installed.display_name,
        content_sha256=installed.content_sha256,
        format_label=installed.format_label,
        format_tier=installed.format_tier,
    )


@router.delete("/pets/{slug}")
async def uninstall_companion_pet(slug: str) -> dict[str, bool]:
    from app.services.companion.pet_store import uninstall_pet

    removed = uninstall_pet(slug)
    if not removed:
        raise HTTPException(status_code=404, detail="Pet not installed")
    await clear_sprite_selection_if_matches(slug)
    return {"removed": True}


@router.get("/pets/{slug}/spritesheet")
async def get_companion_pet_spritesheet(slug: str) -> FileResponse:
    from app.services.companion.pet_store import load_pet, spritesheet_media_type

    pet = load_pet(slug)
    if pet is None or not pet.exists:
        raise HTTPException(status_code=404, detail="Pet spritesheet not found")
    return FileResponse(
        path=pet.spritesheet,
        media_type=spritesheet_media_type(pet.spritesheet),
        filename=pet.spritesheet.name,
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
