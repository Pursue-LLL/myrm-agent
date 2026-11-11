'use client';

/**
 * [INPUT]
 * - @/hooks/voice/voiceDeviceSettings::VOICE_SETTING_KEYS, voiceDeviceSettings (POS: shared voice settings store)
 * - ../../ConfigToggleItem (POS: labelled switch row)
 * - ../SettingsSection (POS: settings card with a title)
 *
 * [OUTPUT]
 * - VoiceSessionToggles: the on/off switches of the voice session.
 *
 * [POS]
 * Settings card for the voice session switches. They are kept on this device, and the chat's voice button reads
 * the same store, so a browser that refuses storage still follows what the switches say until the page closes.
 */

import { useSyncExternalStore, type ComponentProps } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowDataTransferHorizontalIcon, Mic01Icon, Video01Icon, Wifi01Icon } from 'hugeicons-react';
import { VOICE_SETTING_KEYS, voiceDeviceSettings } from '@/hooks/voice/voiceDeviceSettings';
import ConfigToggleItem from '../../ConfigToggleItem';
import SettingsSection from '../SettingsSection';

interface VoiceFlag {
  storageKey: string;
  /** What the switch shows when nobody has touched it. */
  defaultOn: boolean;
  icon: ComponentProps<typeof ConfigToggleItem>['icon'];
  titleKey: string;
  descriptionKey: string;
}

const VOICE_FLAGS: readonly VoiceFlag[] = [
  {
    storageKey: VOICE_SETTING_KEYS.sessionEnabled,
    defaultOn: false,
    icon: Mic01Icon,
    titleKey: 'enableVoiceSession',
    descriptionKey: 'enableVoiceSessionDesc',
  },
  {
    storageKey: VOICE_SETTING_KEYS.fullDuplex,
    defaultOn: true,
    icon: ArrowDataTransferHorizontalIcon,
    titleKey: 'fullDuplex',
    descriptionKey: 'fullDuplexDesc',
  },
  {
    storageKey: VOICE_SETTING_KEYS.cameraEnabled,
    defaultOn: false,
    icon: Video01Icon,
    titleKey: 'enableCamera',
    descriptionKey: 'enableCameraDesc',
  },
  {
    storageKey: VOICE_SETTING_KEYS.agentBridge,
    defaultOn: false,
    icon: Wifi01Icon,
    titleKey: 'agentBridge',
    descriptionKey: 'agentBridgeDesc',
  },
];

function VoiceFlagToggle({ flag }: { flag: VoiceFlag }) {
  const t = useTranslations('voiceSession');
  const checked = useSyncExternalStore(
    voiceDeviceSettings.subscribe,
    () => {
      const stored = voiceDeviceSettings.read(flag.storageKey);
      return flag.defaultOn ? stored !== 'false' : stored === 'true';
    },
    () => flag.defaultOn,
  );

  return (
    <ConfigToggleItem
      icon={flag.icon}
      title={t(flag.titleKey)}
      description={t(flag.descriptionKey)}
      checked={checked}
      onCheckedChange={(next) => voiceDeviceSettings.write(flag.storageKey, String(next))}
    />
  );
}

export default function VoiceSessionToggles() {
  const t = useTranslations('voiceSession');

  return (
    <SettingsSection title={t('enableVoiceSession')}>
      <div className="flex flex-col space-y-4">
        {VOICE_FLAGS.map((flag) => (
          <VoiceFlagToggle key={flag.storageKey} flag={flag} />
        ))}
      </div>
    </SettingsSection>
  );
}
