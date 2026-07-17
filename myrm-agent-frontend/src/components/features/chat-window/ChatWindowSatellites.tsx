'use client';

import dynamic from 'next/dynamic';
import SubagentDashboard from './SubagentDashboard';

const VisualDesktopToggle = dynamic(
  () =>
    import('@/components/features/app-shell/VisualDesktopToggle').then((module) => ({
      default: module.VisualDesktopToggle,
    })),
  { ssr: false },
);

const BrowserInspectorToggle = dynamic(
  () =>
    import('@/components/features/browser-inspector').then((module) => ({
      default: module.BrowserInspectorToggle,
    })),
  { ssr: false },
);

const BrowserLiveView = dynamic(
  () =>
    import('@/components/features/browser-inspector').then((module) => ({
      default: module.BrowserLiveView,
    })),
  { ssr: false },
);

const BrowserRecordingToggle = dynamic(
  () =>
    import('@/components/features/browser-recording').then((module) => ({
      default: module.BrowserRecordingToggle,
    })),
  { ssr: false },
);

const BrowserRecordingPanel = dynamic(
  () =>
    import('@/components/features/browser-recording').then((module) => ({
      default: module.BrowserRecordingPanel,
    })),
  { ssr: false },
);

const DesktopInspectorToggle = dynamic(
  () =>
    import('@/components/features/desktop-inspector').then((module) => ({
      default: module.DesktopInspectorToggle,
    })),
  { ssr: false },
);

const DesktopLiveView = dynamic(
  () =>
    import('@/components/features/desktop-inspector').then((module) => ({
      default: module.DesktopLiveView,
    })),
  { ssr: false },
);

const FileSnapshotPanel = dynamic(
  () =>
    import('@/components/features/checkpoint').then((module) => ({
      default: module.FileSnapshotPanel,
    })),
  { ssr: false },
);

const SessionRevertButton = dynamic(
  () => import('@/components/features/message-actions/SessionRevertButton'),
  { ssr: false },
);

const SubagentPromptButton = dynamic(() => import('./SubagentPromptButton'), { ssr: false });

const PetOverlay = dynamic(() => import('../companion/sprite/PetOverlay'), { ssr: false });

interface ChatWindowSatellitesProps {
  chatId?: string;
  onInspectorInstruction: (instruction: string, refId: string | null) => void;
  onDesktopInspectorInstruction: (instruction: string, refId: string | null) => void;
}

export default function ChatWindowSatellites({
  chatId,
  onInspectorInstruction,
  onDesktopInspectorInstruction,
}: ChatWindowSatellitesProps) {
  return (
    <>
      <VisualDesktopToggle />
      <BrowserInspectorToggle />
      <BrowserLiveView onSendInstruction={onInspectorInstruction} />
      <BrowserRecordingToggle />
      <BrowserRecordingPanel />
      <DesktopInspectorToggle />
      <DesktopLiveView onSendInstruction={onDesktopInspectorInstruction} />
      <FileSnapshotPanel />
      {chatId ? (
        <div className="fixed bottom-24 right-[4.5rem] z-50 max-sm:bottom-20 max-sm:right-16 bg-secondary rounded-full shadow-lg">
          <SessionRevertButton sessionId={chatId} />
        </div>
      ) : null}
      <SubagentPromptButton />
      <SubagentDashboard chatId={chatId} />
      <PetOverlay />
    </>
  );
}

export const GoalStatusCard = dynamic(
  () => import('./goals/GoalStatusCard').then((module) => ({ default: module.GoalStatusCard })),
  { ssr: false },
);

export const GoalControlPlane = dynamic(
  () => import('./goals/GoalControlPlane').then((module) => ({ default: module.GoalControlPlane })),
  { ssr: false },
);

export const LifeStatusCapsule = dynamic(
  () => import('./LifeStatusCapsule').then((module) => ({ default: module.LifeStatusCapsule })),
  { ssr: false },
);
