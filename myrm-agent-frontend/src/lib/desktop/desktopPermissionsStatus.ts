/**
 * [INPUT]
 * - GET /webui/desktop/permissions JSON body (server ↔ harness PermissionStatus)
 *
 * [OUTPUT]
 * - DesktopPermissionsStatus: shared FE contract for desktop OS grant + capture readiness
 * - desktopPermissionsPath: URL helper (optional probe_capture)
 *
 * [POS]
 * Single FE DTO for desktop permissions API. Consumed by Agent Inline, Settings card, Inspector banner.
 */

export type DesktopPermissionsStatus = {
  accessibility: boolean;
  screen_recording: boolean;
  screen_recording_capturable: boolean | null;
  all_granted: boolean;
  capture_ready: boolean;
  platform: string;
  settings_deeplinks: Record<string, string>;
};

export function desktopPermissionsPath(probeCapture = false): string {
  return probeCapture
    ? '/webui/desktop/permissions?probe_capture=true'
    : '/webui/desktop/permissions';
}
