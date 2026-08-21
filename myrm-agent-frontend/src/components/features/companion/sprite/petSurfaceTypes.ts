/**
 * Pet surface IPC/event payload types (main window SSOT → popped-out puppet window).
 */

import type { PetState } from './PetStateMachine';

export type PetSurfaceMode = 'embedded' | 'popped-out';

export type PetSurfaceVoiceState = 'idle' | 'listening' | 'processing' | 'speaking';

export interface PetSurfaceBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Full mirror payload pushed to the OS overlay webview. */
export interface PetSurfaceStatePayload {
  sheetUrl: string;
  sheetRows: number;
  petSize: number;
  petState: PetState;
  blockedOnUser: boolean;
  loading: boolean;
  unread: boolean;
  activeChatId: string | null;
  voiceState?: PetSurfaceVoiceState;
  audioLevel?: number;
}

export type PetSurfaceControl =
  | { type: 'ready' }
  | { type: 'pop-in' }
  | { type: 'submit'; text: string }
  | { type: 'open-app' }
  | { type: 'toggle-app' }
  | { type: 'clear-unread' }
  | { type: 'voice-toggle' }
  | { type: 'voice-interrupt' }
  | { type: 'voice-ptt-start' }
  | { type: 'voice-ptt-stop' }
  | { type: 'bounds'; bounds: PetSurfaceBounds };

export const PET_SURFACE_STATE_EVENT = 'pet-surface-state';
export const PET_SURFACE_CONTROL_EVENT = 'pet-surface-control';

export const PET_SURFACE_WINDOW_LABEL = 'pet-surface';
