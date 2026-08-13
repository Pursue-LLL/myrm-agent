/**
 * [INPUT]
 * - @/lib/tauri (POS: Tauri 环境检测)
 * - @tauri-apps/api (POS: invoke + event emit/listen)
 * - petSurfaceTypes (POS: IPC/event payload types)
 *
 * [OUTPUT]
 * - showPetSurface / hidePetSurface / setPetSurfaceIgnoreCursor / setPetSurfaceFocusable
 * - focusPetSurfaceMainWindow / togglePetSurfaceMainWindow
 * - emitPetSurfaceState / listenPetSurfaceState / emitPetSurfaceControl / listenPetSurfaceControl
 * - isTauriEnv
 *
 * [POS]
 * Tauri bridge for pet surface (embedded host + popped-out OS webview puppet).
 */

import { emitTo, listen, type UnlistenFn } from '@tauri-apps/api/event';

import { isTauriEnvironment } from '@/lib/tauri';

import {
  PET_SURFACE_CONTROL_EVENT,
  PET_SURFACE_STATE_EVENT,
  PET_SURFACE_WINDOW_LABEL,
  type PetSurfaceBounds,
  type PetSurfaceControl,
  type PetSurfaceStatePayload,
} from './petSurfaceTypes';

export { isTauriEnvironment as isTauriEnv };

async function invoke<T = void>(cmd: string, args?: Record<string, unknown>): Promise<T | null> {
  try {
    if (!isTauriEnvironment()) {return null;}
    const { invoke: tauriInvoke } = await import('@tauri-apps/api/core');
    return await tauriInvoke<T>(cmd, args);
  } catch (error) {
    console.warn(`[petSurfaceBridge] ${cmd} failed:`, error);
    return null;
  }
}

export async function showPetSurface(bounds: PetSurfaceBounds): Promise<void> {
  await invoke('show_pet_surface', { payload: bounds });
}

export async function hidePetSurface(): Promise<void> {
  await invoke('hide_pet_surface');
}

export async function setPetSurfaceIgnoreCursor(ignore: boolean): Promise<void> {
  await invoke('pet_surface_set_ignore_cursor', { ignore });
}

export async function setPetSurfaceFocusable(focusable: boolean): Promise<void> {
  await invoke('pet_surface_set_focusable', { focusable });
}

export async function focusPetSurfaceMainWindow(): Promise<void> {
  await invoke('pet_surface_focus_main_window');
}

export async function togglePetSurfaceMainWindow(): Promise<void> {
  await invoke('pet_surface_toggle_main_window');
}

export async function emitPetSurfaceState(payload: PetSurfaceStatePayload): Promise<void> {
  if (!isTauriEnvironment()) {return;}
  await emitTo(PET_SURFACE_WINDOW_LABEL, PET_SURFACE_STATE_EVENT, payload);
}

export async function listenPetSurfaceState(
  handler: (payload: PetSurfaceStatePayload) => void,
): Promise<UnlistenFn> {
  return listen<PetSurfaceStatePayload>(PET_SURFACE_STATE_EVENT, (event) => {
    handler(event.payload);
  });
}

export async function emitPetSurfaceControl(control: PetSurfaceControl): Promise<void> {
  if (!isTauriEnvironment()) {return;}
  await emitTo('main', PET_SURFACE_CONTROL_EVENT, control);
}

export async function listenPetSurfaceControl(
  handler: (control: PetSurfaceControl) => void,
): Promise<UnlistenFn> {
  return listen<PetSurfaceControl>(PET_SURFACE_CONTROL_EVENT, (event) => {
    handler(event.payload);
  });
}
