/**
 * [INPUT]
 * @/lib/moaPresetUtils::MOA_PRESET_IDS (POS: valid MoA preset id SSOT)
 *
 * [OUTPUT]
 * readStoredMoaPresetId / writeStoredMoaPresetId / clearStoredMoaPresetId /
 * resolveHydratedMoaPresetId — hydrate from server DB (preferred) then localStorage
 * persistMoaPresetToServer — PATCH chat preset with rollback + toast on failure
 *
 * [POS]
 * Per-chat MoA preset persistence in localStorage (survives full page refresh; skipped in incognito).
 */

import { MOA_PRESET_IDS, type MoaPresetId } from '@/lib/moaPresetUtils';
import { updateChatActiveMoaPreset } from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';

const STORAGE_PREFIX = 'moaPreset:';

function storageKey(chatId: string): string {
  return `${STORAGE_PREFIX}${chatId}`;
}

function isValidPresetId(value: string | null): value is MoaPresetId {
  return value !== null && (MOA_PRESET_IDS as readonly string[]).includes(value);
}

export function readStoredMoaPresetId(chatId: string | undefined): string | null {
  if (typeof window === 'undefined' || !chatId) {
    return null;
  }
  const raw = localStorage.getItem(storageKey(chatId));
  return isValidPresetId(raw) ? raw : null;
}

export function writeStoredMoaPresetId(chatId: string | undefined, presetId: string | null): void {
  if (typeof window === 'undefined' || !chatId) {
    return;
  }
  const key = storageKey(chatId);
  if (presetId && isValidPresetId(presetId)) {
    localStorage.setItem(key, presetId);
    return;
  }
  localStorage.removeItem(key);
}

export function clearStoredMoaPresetId(chatId: string | undefined): void {
  writeStoredMoaPresetId(chatId, null);
}

export interface HydrateMoaPresetOptions {
  actionMode: string;
  incognitoMode: boolean;
}

/** Hydrate session MoA preset from storage only when agent mode and not incognito. */
export function resolveHydratedMoaPresetId(
  chatId: string | undefined,
  options: HydrateMoaPresetOptions,
  serverPresetId?: string | null,
): string | null {
  if (options.actionMode !== 'agent' || options.incognitoMode) {
    return null;
  }
  if (serverPresetId && isValidPresetId(serverPresetId)) {
    return serverPresetId;
  }
  return readStoredMoaPresetId(chatId);
}

/** Persist session MoA preset to server; optional rollback when PATCH fails. */
export async function persistMoaPresetToServer(
  chatId: string,
  presetId: string | null,
  onFailure?: () => void,
): Promise<void> {
  try {
    await updateChatActiveMoaPreset(chatId, presetId);
  } catch {
    onFailure?.();
    showI18nToast('settings.defaultModel.moaPreset.persistFailed', undefined, { type: 'error' });
  }
}
