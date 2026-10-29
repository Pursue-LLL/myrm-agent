'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import DesktopControlApprovalOverlay from '@/components/features/desktop-inspector/DesktopControlApprovalOverlay';
import SubagentDashboard from './subagent/SubagentDashboard';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import useChatStore from '@/store/useChatStore';
import { useClosePanelOnChatSwitch } from '@/hooks/inspector/useClosePanelOnChatSwitch';
import { usePresenceReadMark } from '@/hooks/chat/usePresenceReadMark';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import { useWidgetBridgeStore } from '@/components/features/widget';

const VisualDesktopToggle = dynamic(
  () =>
    import('@/components/features/app-shell/VisualDesktopToggle').then((module) => ({
      default: module.VisualDesktopToggle,
    })),
  { ssr: false },
);

const ExtensionTakeoverBanner = dynamic(() => import('@/components/features/chat-window/ExtensionTakeoverBanner'), {
  ssr: false,
});

const DashboardWorkspaceDrawer = dynamic(
  () =>
    import('@/components/features/dashboard-workspace').then((module) => ({
      default: module.DashboardWorkspaceDrawer,
    })),
  { ssr: false },
);

const ActiveSubagentSwimlanesBar = dynamic(
  () =>
    import('./in-flight-steer').then((module) => ({
      default: module.ActiveSubagentSwimlanesBar,
    })),
  { ssr: false },
);

const TaskExecutionTimelineDrawer = dynamic(
  () =>
    import('@/components/features/task-inspector').then((module) => ({
      default: module.TaskExecutionTimelineDrawer,
    })),
  { ssr: false },
);

const ReconnectStatusPill = dynamic(
  () =>
    import('@/components/features/reconnect-protocol').then((module) => ({
      default: module.ReconnectStatusPill,
    })),
  { ssr: false },
);

const CommandMatrixModal = dynamic(
  () =>
    import('@/components/features/commands').then((module) => ({
      default: module.CommandMatrixModal,
    })),
  { ssr: false },
);

const WidgetGeneratorModal = dynamic(
  () =>
    import('@/components/features/widget').then((module) => ({
      default: module.WidgetGeneratorModal,
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

const DigitalSelfDraftInboxSatellite = dynamic(() => import('./digital-self/DigitalSelfDraftInboxSatellite'), {
  ssr: false,
});

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

const FileSnapshotPanel = dynamic(() => import('@/components/features/checkpoint/FileSnapshotPanel'), { ssr: false });

const SessionRevertButton = dynamic(() => import('@/components/features/message-actions/SessionRevertButton'), {
  ssr: false,
});

const SubagentPromptButton = dynamic(() => import('./SubagentPromptButton'), { ssr: false });

const StartupRecoveryDialog = dynamic(
  () =>
    import('@/components/features/agent-recovery/StartupRecoveryDialog').then((module) => ({
      default: module.StartupRecoveryDialog,
    })),
  { ssr: false },
);

const PetOverlay = dynamic(() => import('../companion/sprite/PetOverlay'), { ssr: false });

const PetPalette = dynamic(() => import('../companion/PetPalette'), { ssr: false });

const PreferenceRadarToggle = dynamic(
  () => import('./PreferenceRadarToggle').then((m) => ({ default: m.PreferenceRadarToggle })),
  { ssr: false },
);

const ContextFootprintInspector = dynamic(() => import('./ContextFootprintInspector'), {
  ssr: false,
});

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
  const [isContextInspectorOpen, setIsContextInspectorOpen] = useState(false);

  useEffect(() => {
    const handleOpen = () => setIsContextInspectorOpen(true);
    window.addEventListener('myrm:open-context-inspector', handleOpen);
    return () => {
      window.removeEventListener('myrm:open-context-inspector', handleOpen);
    };
  }, []);

  const isCompanionEnabled = useFeatureGateStore((s) => s.isEnabled('companion_mode'));
  const recoveryDialogOpen = useChatStore((s) => s.recoveryDialogOpen);
  const recoveryAgentId = useChatStore((s) => s.recoveryAgentId);
  const closeRecoveryDialog = useChatStore((s) => s.closeRecoveryDialog);

  const storeChatId = useChatStore((s) => s.chatId?.trim() ?? '');
  const effectiveChatId = storeChatId || chatId?.trim() || '';
  const hasMessages = useChatStore((s) => s.messages.length > 0);
  usePresenceReadMark(effectiveChatId, hasMessages);

  const isBrowserInspectorOpen = useBrowserInspectorStore((s) => s.isOpen);
  const closeBrowserInspector = useBrowserInspectorStore((s) => s.closePanel);
  useClosePanelOnChatSwitch(effectiveChatId, isBrowserInspectorOpen, closeBrowserInspector);

  const isDesktopInspectorOpen = useDesktopInspectorStore((s) => s.isOpen);
  const closeDesktopInspector = useDesktopInspectorStore((s) => s.closePanel);
  useClosePanelOnChatSwitch(effectiveChatId, isDesktopInspectorOpen, closeDesktopInspector);

  const isGeneratorModalOpen = useWidgetBridgeStore((s) => s.isGeneratorModalOpen);
  const setGeneratorModalOpen = useWidgetBridgeStore((s) => s.setGeneratorModalOpen);

  return (
    <>
      <DesktopControlApprovalOverlay />
      <ExtensionTakeoverBanner />
      <VisualDesktopToggle />
      <BrowserInspectorToggle />
      <BrowserLiveView onSendInstruction={onInspectorInstruction} />
      <BrowserRecordingToggle />
      <BrowserRecordingPanel />
      <DesktopInspectorToggle />
      <DesktopLiveView onSendInstruction={onDesktopInspectorInstruction} />
      <FileSnapshotPanel />
      <PreferenceRadarToggle chatId={chatId} />
      {chatId ? (
        <div className="fixed bottom-24 right-[4.5rem] z-50 max-sm:bottom-20 max-sm:right-16 bg-secondary rounded-full shadow-lg">
          <SessionRevertButton sessionId={chatId} />
        </div>
      ) : null}
      <SubagentPromptButton />
      <SubagentDashboard chatId={chatId} />
      {recoveryDialogOpen && recoveryAgentId ? (
        <StartupRecoveryDialog
          agentId={recoveryAgentId}
          open={recoveryDialogOpen}
          onOpenChange={(open) => {
            if (!open) {
              closeRecoveryDialog();
            }
          }}
        />
      ) : null}
      {isCompanionEnabled ? (
        <>
          <PetOverlay />
          <PetPalette />
        </>
      ) : null}
      <ContextFootprintInspector open={isContextInspectorOpen} onClose={() => setIsContextInspectorOpen(false)} />
      <TaskExecutionTimelineDrawer />
      {chatId ? (
        <div className="fixed top-3.5 right-28 z-40 max-sm:hidden">
          <ReconnectStatusPill sessionId={chatId} />
        </div>
      ) : null}
      <CommandMatrixModal />
      {effectiveChatId && isGeneratorModalOpen ? (
        <WidgetGeneratorModal
          chatId={effectiveChatId}
          isOpen={isGeneratorModalOpen}
          onClose={() => setGeneratorModalOpen(false)}
        />
      ) : null}

      <DigitalSelfDraftInboxSatellite />
      <DashboardWorkspaceDrawer />
      <ActiveSubagentSwimlanesBar />
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
