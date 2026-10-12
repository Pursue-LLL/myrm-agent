/**
 * [INPUT]
 * — (constants only)
 *
 * [OUTPUT]
 * - MYRM_LOCKED_USE_SETTINGS_ANCHOR / MYRM_PRIVACY_CURTAIN_SETTINGS_ANCHOR
 * - scrollToDesktopSettingsAnchor
 *
 * [POS]
 * Shared scroll targets between desktop readiness diagnostics and System settings cards.
 */

export const MYRM_LOCKED_USE_SETTINGS_ANCHOR = 'myrm-locked-use-settings';
export const MYRM_PRIVACY_CURTAIN_SETTINGS_ANCHOR = 'myrm-privacy-curtain-settings';

export function scrollToDesktopSettingsAnchor(anchorId: string): void {
  if (typeof document === 'undefined') {
    return;
  }
  document.getElementById(anchorId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
