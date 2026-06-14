'use client';

import { useVoicePttListener } from '@/hooks/useVoicePttListener';

const VoicePttInitializer = () => {
  useVoicePttListener();
  return null;
};

export default VoicePttInitializer;
