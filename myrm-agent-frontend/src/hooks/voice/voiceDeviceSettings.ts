/**
 * [INPUT]
 * - @/hooks/ui/persistedStringStore::createPersistedStringStore (POS: per-device string memory that survives refused storage)
 *
 * [OUTPUT]
 * - VOICE_SETTING_KEYS: the storage keys of the voice settings kept on this device.
 * - voiceDeviceSettings: the one place those settings are read and written.
 *
 * [POS]
 * The settings pages write these keys and the chat's voice button reads them. Going through one store means a
 * browser that refuses storage still honours the user's choice until the page closes, and every reader hears
 * about a change at once, whether this page or another tab made it. The key names are persisted user data.
 */

import { createPersistedStringStore } from '@/hooks/ui/persistedStringStore';

export const VOICE_SETTING_KEYS = {
  sessionEnabled: 'voiceSessionEnabled',
  fullDuplex: 'voiceFullDuplexEnabled',
  agentBridge: 'voiceAgentBridgeEnabled',
  mode: 'voiceSessionMode',
} as const;

export const voiceDeviceSettings = createPersistedStringStore('');
