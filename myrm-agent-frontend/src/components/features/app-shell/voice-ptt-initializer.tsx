'use client';

import { useVoicePttListener } from '@/hooks/voice/useVoicePttListener';

const VoicePttInitializer = () => {
  useVoicePttListener();
  return null;
};

export default VoicePttInitializer;
