import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearStoredMoaPresetId,
  persistMoaPresetToServer,
  readStoredMoaPresetId,
  resolveHydratedMoaPresetId,
  writeStoredMoaPresetId,
} from '@/store/chat/moaPresetStorage';

vi.mock('@/services/chat', () => ({
  updateChatActiveMoaPreset: vi.fn(),
}));

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: vi.fn(),
}));

const CHAT_ID = 'chat-moa-persist-1';

describe('moaPresetStorage', () => {
  afterEach(() => {
    clearStoredMoaPresetId(CHAT_ID);
  });

  it('round-trips a valid preset id per chat', () => {
    writeStoredMoaPresetId(CHAT_ID, 'review');
    expect(readStoredMoaPresetId(CHAT_ID)).toBe('review');
  });

  it('returns null for unknown preset ids', () => {
    writeStoredMoaPresetId(CHAT_ID, 'not-a-preset');
    expect(readStoredMoaPresetId(CHAT_ID)).toBeNull();
  });

  it('clears storage when preset is null', () => {
    writeStoredMoaPresetId(CHAT_ID, 'fast');
    clearStoredMoaPresetId(CHAT_ID);
    expect(readStoredMoaPresetId(CHAT_ID)).toBeNull();
  });

  it('isolates presets by chat id', () => {
    writeStoredMoaPresetId('chat-a', 'default');
    writeStoredMoaPresetId('chat-b', 'review');
    expect(readStoredMoaPresetId('chat-a')).toBe('default');
    expect(readStoredMoaPresetId('chat-b')).toBe('review');
    clearStoredMoaPresetId('chat-a');
    clearStoredMoaPresetId('chat-b');
  });

  it('resolveHydratedMoaPresetId skips incognito and non-agent modes', () => {
    writeStoredMoaPresetId(CHAT_ID, 'review');
    expect(resolveHydratedMoaPresetId(CHAT_ID, { actionMode: 'agent', incognitoMode: false })).toBe('review');
    expect(resolveHydratedMoaPresetId(CHAT_ID, { actionMode: 'agent', incognitoMode: true })).toBeNull();
    expect(resolveHydratedMoaPresetId(CHAT_ID, { actionMode: 'fast', incognitoMode: false })).toBeNull();
  });

  it('prefers server preset over localStorage when both exist', () => {
    writeStoredMoaPresetId(CHAT_ID, 'fast');
    expect(resolveHydratedMoaPresetId(CHAT_ID, { actionMode: 'agent', incognitoMode: false }, 'review')).toBe('review');
  });

  it('keeps localStorage preset when leaving agent mode (caller clears memory only)', () => {
    writeStoredMoaPresetId(CHAT_ID, 'default');
    expect(resolveHydratedMoaPresetId(CHAT_ID, { actionMode: 'fast', incognitoMode: false })).toBeNull();
    expect(readStoredMoaPresetId(CHAT_ID)).toBe('default');
    expect(resolveHydratedMoaPresetId(CHAT_ID, { actionMode: 'agent', incognitoMode: false })).toBe('default');
  });

  it('persistMoaPresetToServer invokes rollback and toast when PATCH fails', async () => {
    const { updateChatActiveMoaPreset } = await import('@/services/chat');
    const { showI18nToast } = await import('@/services/i18nToastService');
    vi.mocked(updateChatActiveMoaPreset).mockRejectedValueOnce(new Error('network'));
    const rollback = vi.fn();
    await persistMoaPresetToServer(CHAT_ID, 'default', rollback);
    expect(rollback).toHaveBeenCalledOnce();
    expect(showI18nToast).toHaveBeenCalledWith('settings.defaultModel.moaPreset.persistFailed', undefined, {
      type: 'error',
    });
  });
});
