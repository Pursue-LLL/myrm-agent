"""Install inspected theme packages into FilesService-backed profiles.

[INPUT]
app.core.storage::files_service (POS: 文件存储写入)
app.schemas.theme_profile::ThemeProfileRecipeModel (POS: 主题配方模型)
app.services.theme.package.manifest::to_installed_profile (POS: manifest → recipe 转换)
app.services.theme.package.session_store (POS: inspect 会话消费)

[OUTPUT]
install_theme_package(session_id) -> ThemeProfileRecipeModel

[POS]
消费 inspect session，将包内资产上传到 FilesService 并替换 asset ref，
输出可直接写入 personalSettings 的 ThemeProfileRecipe。
"""

from __future__ import annotations

import uuid

from app.core.storage import files_service
from app.schemas.theme_profile import ThemeProfileRecipeModel
from app.services.theme.package.manifest import to_installed_profile
from app.services.theme.package.session_store import ThemePackageInspectSession, consume_session


class ThemePackageInstallError(ValueError):
    """User-facing install failure."""


async def install_theme_package(
    session_id: str,
    *,
    set_active: bool,
    existing_profile_ids: set[str],
) -> tuple[ThemeProfileRecipeModel, bool]:
    session = consume_session(session_id)
    if session is None:
        raise ThemePackageInstallError("Theme import session expired or not found")
    if not session.can_import:
        raise ThemePackageInstallError("Theme package cannot be imported due to validation warnings")

    profile_id = _allocate_profile_id(existing_profile_ids)
    hero_file_id = await _upload_member(session, session.hero_filename)
    poster_file_id = await _upload_member(session, session.manifest.profile.art.posterAssetRef)
    preview_file_id = await _upload_member(session, session.preview_filename)

    profile = to_installed_profile(
        session.manifest,
        profile_id=profile_id,
        hero_file_id=hero_file_id,
        poster_file_id=poster_file_id,
        preview_file_id=preview_file_id,
    )
    return profile, set_active


def _allocate_profile_id(existing_ids: set[str]) -> str:
    while True:
        profile_id = f"imported/{uuid.uuid4().hex}"
        if profile_id not in existing_ids:
            return profile_id


async def _upload_member(session: ThemePackageInspectSession, filename: str | None) -> str | None:
    if not filename:
        return None
    content = session.files.get(filename)
    if content is None:
        raise ThemePackageInstallError(f"Missing packaged asset: {filename}")
    stored = await files_service.upload_file(
        filename=filename,
        content=content,
        content_type=_content_type_for_filename(filename),
    )
    return stored.id


def _content_type_for_filename(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".mp4"):
        return "video/mp4"
    return "application/octet-stream"
