"""Chrome MCP smoke: Appearance theme package section + browser inspect API."""

from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _build_sample_package() -> bytes:
    recipe = {
        "schemaVersion": 1,
        "minEngineVersion": "1.0.0",
        "name": "E2E Theme",
        "description": "Chrome MCP smoke theme",
        "profile": {
            "name": "E2E Theme",
            "layoutId": "full-bleed",
            "fontId": "inter",
            "palette": {
                "primaryLight": "#588e95",
                "primaryDark": "#6ba3aa",
                "primaryHoverLight": "#4a7d84",
                "primaryHoverDark": "#7eb5bc",
                "primaryDarkLight": "#10505a",
                "primaryDarkDark": "#588e95",
                "dualAccent": True,
            },
            "art": {
                "focusX": 0.5,
                "focusY": 0.42,
                "wash": 0.4,
                "mediaKind": "image",
                "assetRef": "hero.png",
            },
        },
    }
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("recipe.json", json.dumps(recipe))
        archive.writestr("hero.png", png)
    return buffer.getvalue()


_APPEARANCE_PACKAGE_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.includes('/settings') &&
      (bodyText.includes('主题包') || bodyText.includes('Theme package')),
    hasImport:
      bodyText.includes('导入主题包') || bodyText.includes('Import theme package'),
    hasExport:
      bodyText.includes('导出当前主题') || bodyText.includes('Export current theme'),
  };
})()"""


_BROWSER_INSPECT_JS = """async (base64Zip) => {
  const binary = atob(base64Zip);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  const file = new File([bytes], 'e2e.myrmtheme', { type: 'application/zip' });
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch('/api/v1/theme/packages/inspect', {
    method: 'POST',
    body: formData,
    credentials: 'include',
  });
  const payload = await response.json();
  return {
    ok: response.ok,
    canImport: payload?.data?.inspect?.canImport === true,
    heroThumbnail: payload?.data?.inspect?.heroThumbnailBase64 ?? null,
    name: payload?.data?.inspect?.name ?? null,
  };
}"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_theme_package_appearance_import_smoke() -> None:
    prepare_e2e_ui_session(get_e2e_api_url())
    zip_b64 = base64.b64encode(_build_sample_package()).decode("ascii")

    warm_ui_route("/settings/preferences")
    with open_settings_subroute(
        "/settings/preferences",
        timeout_ms=90_000,
    ) as (client, page):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            _APPEARANCE_PACKAGE_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert state.get("ready") is True, state
        assert state.get("hasImport") is True, state
        assert state.get("hasExport") is True, state

        inspect_state = client.evaluate(
            page,
            f"({_BROWSER_INSPECT_JS})({json.dumps(zip_b64)})",
            timeout_sec=60.0,
        )
        assert isinstance(inspect_state, dict), inspect_state
        assert inspect_state.get("ok") is True, inspect_state
        assert inspect_state.get("canImport") is True, inspect_state
        assert inspect_state.get("name") == "E2E Theme", inspect_state
        hero = inspect_state.get("heroThumbnail")
        assert isinstance(hero, str) and hero.startswith("data:image/png;base64,"), inspect_state
