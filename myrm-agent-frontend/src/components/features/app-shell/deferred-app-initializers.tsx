'use client';

import dynamic from 'next/dynamic';

import DeferredMount from './deferred-mount';

const FlowPadModal = dynamic(
  () => import('./flow-pad-modal').then((module) => ({ default: module.FlowPadModal })),
  { ssr: false },
);

const PWAUpdater = dynamic(
  () => import('./pwa-updater').then((module) => ({ default: module.PWAUpdater })),
  { ssr: false },
);

const AppUpdatePrompt = dynamic(
  () => import('./app-update-prompt').then((module) => ({ default: module.AppUpdatePrompt })),
  { ssr: false },
);

const WhatsNewModal = dynamic(
  () => import('./whats-new-modal').then((module) => ({ default: module.WhatsNewModal })),
  { ssr: false },
);

const AppshotInitializer = dynamic(() => import('./appshot-initializer'), { ssr: false });

const VoicePttInitializer = dynamic(() => import('./voice-ptt-initializer'), { ssr: false });

export default function DeferredAppInitializers() {
  return (
    <DeferredMount>
      <FlowPadModal />
      <PWAUpdater />
      <AppUpdatePrompt />
      <WhatsNewModal />
      <AppshotInitializer />
      <VoicePttInitializer />
    </DeferredMount>
  );
}
