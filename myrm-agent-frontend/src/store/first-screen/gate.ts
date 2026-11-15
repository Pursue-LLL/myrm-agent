/**
 * [INPUT]
 * - @/lib/deploy-mode::isTauriRuntime / isLocalMode / isRemoteGatewayActive (POS: where the app runs and which backend it talks to)
 * - process.env.NEXT_PUBLIC_FIRST_SCREEN_SNAPSHOT (POS: build-time feature flag)
 *
 * [OUTPUT]
 * - isFirstScreenSnapshotEnabled: whether the first-screen snapshot may be read or written in this runtime.
 *
 * [POS]
 * Feature gate of the first-screen snapshot. The snapshot only pays off where the backend starts after the window opens, and
 * what it stores must belong to the one backend the window talks to: the desktop shell on its own sidecar. A window connected
 * to a remote server never uses it.
 */
import { isLocalMode, isRemoteGatewayActive, isTauriRuntime } from '@/lib/deploy-mode';

/** `desktop` (default): the Tauri window; `local`: every local-mode origin, for browser development; `off`: never. */
type SnapshotMode = 'desktop' | 'local' | 'off';

function snapshotMode(): SnapshotMode {
  const flag = process.env.NEXT_PUBLIC_FIRST_SCREEN_SNAPSHOT?.trim().toLowerCase();
  return flag === 'local' || flag === 'off' ? flag : 'desktop';
}

export function isFirstScreenSnapshotEnabled(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  const mode = snapshotMode();
  if (mode === 'off' || isRemoteGatewayActive()) {
    return false;
  }
  return mode === 'local' ? isLocalMode() : isTauriRuntime();
}
