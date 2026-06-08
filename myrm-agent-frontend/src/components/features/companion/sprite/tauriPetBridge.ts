/**
 * Tauri Pet Overlay Bridge — invokes native Tauri commands for
 * the desktop pet overlay window.
 *
 * Gracefully no-ops when not running inside Tauri (Web/SaaS mode).
 */

async function invoke<T = void>(cmd: string, args?: Record<string, unknown>): Promise<T | null> {
  try {
    if (typeof window === 'undefined') return null;
    const tauri = (window as any).__TAURI__;
    if (!tauri?.core?.invoke) return null;
    return await tauri.core.invoke(cmd, args);
  } catch (e) {
    console.warn(`[tauriPetBridge] ${cmd} failed:`, e);
    return null;
  }
}

export function isTauriEnv(): boolean {
  return typeof window !== 'undefined' && !!(window as any).__TAURI__;
}

export async function showPetOverlay(sheetUrl: string, size?: number, initialRow?: number) {
  return invoke('show_pet_overlay', {
    payload: { sheetUrl, size: size ?? 128, initialRow: initialRow ?? 0 },
  });
}

export async function hidePetOverlay() {
  return invoke('hide_pet_overlay');
}

export async function setPetOverlayRow(row: number) {
  return invoke('pet_overlay_set_row', { row });
}
