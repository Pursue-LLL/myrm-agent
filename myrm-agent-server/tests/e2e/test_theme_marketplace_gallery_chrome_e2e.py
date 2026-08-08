"""Chrome MCP smoke: Theme Studio Gallery free install chain."""

from __future__ import annotations

import json

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
from tests.support.theme_marketplace_e2e import (
    acquire_theme_listing_for_e2e,
    cp_base_url,
    cp_jwt_secret,
    cp_reachable,
    fetch_official_free_listing_id,
    issue_cp_auth_token,
    seed_official_listing,
)

_E2E_USER_ID = "local_user"


_GALLERY_PAGE_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready: location.pathname.includes('/settings/theme-studio'),
    hasGallery:
      bodyText.includes('Theme gallery') ||
      bodyText.includes('主题画廊') ||
      bodyText.includes('Browse official and community themes'),
    hasStudio:
      bodyText.includes('Theme Studio') ||
      bodyText.includes('主题工作室'),
  };
})()"""


_GALLERY_INSTALL_JS = """async (config) => {
  const headers = (token) => {
    const out = { Accept: 'application/json' };
    if (token) out.Authorization = `Bearer ${token}`;
    return out;
  };

  const cpBase = config.cpBase.replace(/\\/+$/, '');
  const listingId = config.listingId;

  const acquireRes = await fetch(`${cpBase}/api/theme-marketplace/listing/${listingId}/acquire`, {
    method: 'POST',
    headers: headers(config.cpToken),
    credentials: 'include',
  });
  if (!acquireRes.ok) {
    return { step: 'acquire', ok: false, status: acquireRes.status };
  }

  const tokenRes = await fetch(
    `${cpBase}/api/theme-marketplace/listing/${listingId}/download-token`,
    { method: 'POST', headers: headers(config.cpToken), credentials: 'include' },
  );
  if (!tokenRes.ok) {
    return { step: 'download-token', ok: false, status: tokenRes.status };
  }
  const tokenPayload = await tokenRes.json();
  const packageSha256 = tokenPayload.package_sha256 ?? tokenPayload.packageSha256;
  const transportSignature =
    tokenPayload.transport_signature ?? tokenPayload.transportSignature;
  const expiresAt = tokenPayload.expires_at ?? tokenPayload.expiresAt;

  const params = new URLSearchParams({
    signature: transportSignature,
    expires_at: String(expiresAt),
  });
  const packageRes = await fetch(
    `${cpBase}/api/theme-marketplace/listing/${listingId}/package?${params.toString()}`,
    { headers: headers(config.cpToken), credentials: 'include' },
  );
  if (!packageRes.ok) {
    return { step: 'package', ok: false, status: packageRes.status };
  }
  const blob = await packageRes.blob();

  const formData = new FormData();
  formData.append('file', blob, 'theme.myrmtheme');
  formData.append('listing_id', listingId);
  formData.append('listing_origin', 'official');
  formData.append('package_sha256', packageSha256);
  formData.append('transport_signature', transportSignature);
  formData.append('expires_at', String(expiresAt));
  formData.append('set_active', 'true');
  formData.append('existing_profile_ids', '[]');

  const installRes = await fetch('/api/v1/theme/packages/install-from-marketplace', {
    method: 'POST',
    headers: headers(config.cpToken),
    body: formData,
    credentials: 'include',
  });
  const installPayload = await installRes.json().catch(() => ({}));
  const profileName = installPayload?.data?.install?.profile?.name ?? null;
  return {
    step: 'install',
    ok: installRes.ok,
    status: installRes.status,
    profileName,
  };
}"""


_GALLERY_UI_CLICK_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const previewBtn = buttons.find((btn) => {
    const text = (btn.textContent || '').trim();
    return text.includes('Preview & install') || text.includes('预览并安装');
  });
  if (!previewBtn) {
    return { clickedPreview: false };
  }
  previewBtn.click();
  return { clickedPreview: true };
})()"""


_GALLERY_CONFIRM_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const confirmBtn = buttons.find((btn) => {
    const text = (btn.textContent || '').trim();
    return text === 'Install' || text === '安装';
  });
  if (!confirmBtn) {
    return { clickedConfirm: false };
  }
  confirmBtn.click();
  return { clickedConfirm: true };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode='SHARED', access_scope='READ', workload='STANDARD'
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_theme_marketplace_gallery_free_install_smoke() -> None:
    if not cp_reachable():
        pytest.skip(f"Control Plane not reachable at {cp_base_url()}")
    if not cp_jwt_secret():
        pytest.skip("MYRM_CP_JWT_SECRET or JWT_SECRET required for CP marketplace auth")

    seed_official_listing()
    cp_token = issue_cp_auth_token(_E2E_USER_ID)
    assert cp_token is not None

    listing_id = fetch_official_free_listing_id(auth_token=cp_token)
    if not listing_id:
        pytest.skip("No published free official theme listing in CP catalog")

    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route('/settings/theme-studio')

    with open_settings_subroute(
        '/settings/theme-studio',
        timeout_ms=90_000,
    ) as (client, page):
        dismiss_blocking_modals(client, page)
        page_state = wait_for_state(
            client,
            page,
            _GALLERY_PAGE_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert page_state.get('ready') is True, page_state
        assert page_state.get('hasStudio') is True, page_state

        client.evaluate(
            page,
            f"localStorage.setItem('auth_token', {json.dumps(cp_token)})",
            timeout_sec=15.0,
        )

        install_config = {
            'cpBase': cp_base_url(),
            'listingId': listing_id,
            'cpToken': cp_token,
        }
        install_state = client.evaluate(
            page,
            f'({_GALLERY_INSTALL_JS})({json.dumps(install_config)})',
            timeout_sec=120.0,
        )
        assert isinstance(install_state, dict), install_state
        assert install_state.get('ok') is True, install_state
        assert install_state.get('step') == 'install', install_state
        assert install_state.get('profileName') == 'Official Default', install_state

        if page_state.get('hasGallery') is True:
            ui_preview = client.evaluate(page, _GALLERY_UI_CLICK_JS, timeout_sec=30.0)
            assert isinstance(ui_preview, dict), ui_preview
            if ui_preview.get('clickedPreview') is True:
                confirm_state = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const text = document.body.innerText || '';
                      return {
                        ready:
                          text.includes('Install theme') ||
                          text.includes('安装主题') ||
                          text.includes('Official Default'),
                      };
                    })()""",
                    timeout_sec=_warm_ui_parallel_wait_sec(60.0),
                )
                assert confirm_state.get('ready') is True, confirm_state
                ui_confirm = client.evaluate(page, _GALLERY_CONFIRM_JS, timeout_sec=30.0)
                assert isinstance(ui_confirm, dict), ui_confirm
                assert ui_confirm.get('clickedConfirm') is True, ui_confirm


_PURCHASE_RETURN_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    completing:
      bodyText.includes('Completing your purchase') ||
      bodyText.includes('正在完成购买'),
    ownedTab:
      bodyText.includes('Owned') ||
      bodyText.includes('已拥有'),
    installed:
      bodyText.includes('Theme installed') ||
      bodyText.includes('主题已安装') ||
      bodyText.includes('Official Default'),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode='SHARED', access_scope='READ', workload='STANDARD'
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_theme_purchased_return_auto_install_smoke() -> None:
    if not cp_reachable():
        pytest.skip(f"Control Plane not reachable at {cp_base_url()}")
    if not cp_jwt_secret():
        pytest.skip("MYRM_CP_JWT_SECRET or JWT_SECRET required for CP marketplace auth")

    seed_official_listing()
    cp_token = issue_cp_auth_token(_E2E_USER_ID)
    assert cp_token is not None

    listing_id = fetch_official_free_listing_id(auth_token=cp_token)
    if not listing_id:
        pytest.skip("No published free official theme listing in CP catalog")

    acquire_theme_listing_for_e2e(listing_id=listing_id, auth_token=cp_token)

    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route('/settings/theme-studio')

    with open_settings_subroute(
        '/settings/theme-studio',
        timeout_ms=90_000,
    ) as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(
            page,
            f"localStorage.setItem('auth_token', {json.dumps(cp_token)})",
            timeout_sec=15.0,
        )
        client.evaluate(
            page,
            f"window.location.href = {json.dumps(f'/settings/theme-studio?theme_purchased={listing_id}')}",
            timeout_sec=30.0,
        )

        final_state = wait_for_state(
            client,
            page,
            _PURCHASE_RETURN_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert isinstance(final_state, dict), final_state
        assert final_state.get('installed') is True, final_state
