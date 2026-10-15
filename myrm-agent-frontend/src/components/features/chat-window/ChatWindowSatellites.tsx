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
import useDeviceInspectorStore from '@/store/useDeviceInspectorStore';
import { useUiAlignmentStore } from '@/components/features/artifacts/ui_alignment';
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

const UiVariantCompareViewer = dynamic(
  () =>
    import('@/components/features/artifacts/ui_alignment').then((module) => ({
      default: module.UiVariantCompareViewer,
    })),
  { ssr: false },
);

const DelightTemplateGalleryModal = dynamic(
  () =>
    import('@/components/features/templates/delight').then((module) => ({
      default: module.DelightTemplateGalleryModal,
    })),
  { ssr: false },
);

const SingleFileSandboxShowcase = dynamic(
  () =>
    import('@/components/features/templates/delight').then((module) => ({
      default: module.SingleFileSandboxShowcase,
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

const DigitalSelfDraftInboxSatellite = dynamic(
  () => import('./digital-self/DigitalSelfDraftInboxSatellite'),
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

const DeviceInspectorToggle = dynamic(
  () =>
    import('@/components/features/device-inspector').then((module) => ({
      default: module.DeviceInspectorToggle,
    })),
  { ssr: false },
);

const DeviceLiveView = dynamic(
  () =>
    import('@/components/features/device-inspector').then((module) => ({
      default: module.DeviceLiveView,
    })),
  { ssr: false },
);

const TaskSpaceDock = dynamic(
  () =>
    import('@/components/features/browser/TaskSpaceDock').then((module) => ({
      default: module.TaskSpaceDock,
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

const OrderedReportSettlementFeed = dynamic(
  () => import('./OrderedReportSettlementFeed').then((m) => ({ default: m.OrderedReportSettlementFeed })),
  { ssr: false },
);

const SubagentFailureFactBanner = dynamic(
  () => import('./SubagentFailureFactBanner').then((m) => ({ default: m.SubagentFailureFactBanner })),
  { ssr: false },
);

const AgentDebateStream = dynamic(
  () => import('./AgentDebateStream').then((m) => ({ default: m.AgentDebateStream })),
  { ssr: false },
);

const ExternalAgentProcessLane = dynamic(
  () => import('./ExternalAgentProcessLane').then((m) => ({ default: m.ExternalAgentProcessLane })),
  { ssr: false },
);

const DebateTradeoffMatrixCard = dynamic(
  () => import('./DebateTradeoffMatrixCard').then((m) => ({ default: m.DebateTradeoffMatrixCard })),
  { ssr: false },
);

const LiveTeamSupervisionKanban = dynamic(
  () => import('./LiveTeamSupervisionKanban').then((m) => ({ default: m.LiveTeamSupervisionKanban })),
  { ssr: false },
);

const SubagentFailurePolicyCard = dynamic(
  () => import('./SubagentFailurePolicyCard').then((m) => ({ default: m.SubagentFailurePolicyCard })),
  { ssr: false },
);

const WorkspaceTeamBlueprintBar = dynamic(
  () => import('./WorkspaceTeamBlueprintBar').then((m) => ({ default: m.WorkspaceTeamBlueprintBar })),
  { ssr: false },
);

const SafeTeamDesignGuardrailsCard = dynamic(
  () => import('./SafeTeamDesignGuardrailsCard').then((m) => ({ default: m.SafeTeamDesignGuardrailsCard })),
  { ssr: false },
);

const AutonomousLoopModePill = dynamic(
  () => import('./AutonomousLoopModePill').then((m) => ({ default: m.AutonomousLoopModePill })),
  { ssr: false },
);

const CreatorModeStudioModal = dynamic(
  () => import('./CreatorModeStudioModal').then((m) => ({ default: m.CreatorModeStudioModal })),
  { ssr: false },
);

const TriRolePipelinePanel = dynamic(
  () => import('./TriRolePipelinePanel').then((m) => ({ default: m.TriRolePipelinePanel })),
  { ssr: false },
);

const SkillBundleWarmupModal = dynamic(
  () => import('./SkillBundleWarmupModal').then((m) => ({ default: m.SkillBundleWarmupModal })),
  { ssr: false },
);

const MultiBotFocusIndicator = dynamic(
  () => import('./MultiBotFocusIndicator').then((m) => ({ default: m.MultiBotFocusIndicator })),
  { ssr: false },
);

const McpPayloadSummarizerCard = dynamic(
  () => import('./McpPayloadSummarizerCard').then((m) => ({ default: m.McpPayloadSummarizerCard })),
  { ssr: false },
);

const CodingWavePresetModal = dynamic(
  () => import('./CodingWavePresetModal').then((m) => ({ default: m.CodingWavePresetModal })),
  { ssr: false },
);

const SubagentLifecycleToolchainCard = dynamic(
  () => import('./SubagentLifecycleToolchainCard').then((m) => ({ default: m.SubagentLifecycleToolchainCard })),
  { ssr: false },
);

const MixedFleetPresetCard = dynamic(
  () => import('./MixedFleetPresetCard').then((m) => ({ default: m.MixedFleetPresetCard })),
  { ssr: false },
);

const ZeroTokenContractCard = dynamic(
  () => import('./ZeroTokenContractCard').then((m) => ({ default: m.ZeroTokenContractCard })),
  { ssr: false },
);

const CrossSurfaceActivityBridgeCard = dynamic(
  () => import('./CrossSurfaceActivityBridgeCard').then((m) => ({ default: m.CrossSurfaceActivityBridgeCard })),
  { ssr: false },
);

const MultiLaneParallelExecutionCard = dynamic(
  () => import('./MultiLaneParallelExecutionCard').then((m) => ({ default: m.MultiLaneParallelExecutionCard })),
  { ssr: false },
);

const DeterministicSessionForkCard = dynamic(
  () => import('./DeterministicSessionForkCard').then((m) => ({ default: m.DeterministicSessionForkCard })),
  { ssr: false },
);

const SharedTokenBudgetGovernanceCard = dynamic(
  () => import('./SharedTokenBudgetGovernanceCard').then((m) => ({ default: m.SharedTokenBudgetGovernanceCard })),
  { ssr: false },
);

const PipelineIntegrityDoctorCard = dynamic(
  () => import('./PipelineIntegrityDoctorCard').then((m) => ({ default: m.PipelineIntegrityDoctorCard })),
  { ssr: false },
);

const ConversationalSpecialistSummoningCard = dynamic(
  () => import('./ConversationalSpecialistSummoningCard').then((m) => ({ default: m.ConversationalSpecialistSummoningCard })),
  { ssr: false },
);

const SwarmTopologyMeshCard = dynamic(
  () => import('./SwarmTopologyMeshCard').then((m) => ({ default: m.SwarmTopologyMeshCard })),
  { ssr: false },
);

const SubagentWorkspaceInheritanceCard = dynamic(
  () => import('./SubagentWorkspaceInheritanceCard').then((m) => ({ default: m.SubagentWorkspaceInheritanceCard })),
  { ssr: false },
);

const SubagentReplayDedupHarmonizerCard = dynamic(
  () => import('./SubagentReplayDedupHarmonizerCard').then((m) => ({ default: m.SubagentReplayDedupHarmonizerCard })),
  { ssr: false },
);

const SubagentCloudEdgeRelayCard = dynamic(
  () => import('./SubagentCloudEdgeRelayCard').then((m) => ({ default: m.SubagentCloudEdgeRelayCard })),
  { ssr: false },
);

const VirtualRoomCoDevCockpitCard = dynamic(
  () => import('./VirtualRoomCoDevCockpitCard').then((m) => ({ default: m.VirtualRoomCoDevCockpitCard })),
  { ssr: false },
);

const HighConcurrencySwarmOffloadCard = dynamic(
  () => import('./HighConcurrencySwarmOffloadCard').then((m) => ({ default: m.HighConcurrencySwarmOffloadCard })),
  { ssr: false },
);

const VisualTimelineCherryPickCard = dynamic(
  () => import('./VisualTimelineCherryPickCard').then((m) => ({ default: m.VisualTimelineCherryPickCard })),
  { ssr: false },
);

const CleanCodeAssemblyPipelineCard = dynamic(
  () => import('./CleanCodeAssemblyPipelineCard').then((m) => ({ default: m.CleanCodeAssemblyPipelineCard })),
  { ssr: false },
);

const LightweightFusenBoardCard = dynamic(
  () => import('./LightweightFusenBoardCard').then((m) => ({ default: m.LightweightFusenBoardCard })),
  { ssr: false },
);





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
  const [isReportFifoOpen, setIsReportFifoOpen] = useState(false);
  const [isFailureFactsOpen, setIsFailureFactsOpen] = useState(false);
  const [currentFailureFact, setCurrentFailureFact] = useState<import('./SubagentFailureFactBanner').StructuredFailureFactItem | null>(null);
  const [isDebateStreamOpen, setIsDebateStreamOpen] = useState(false);
  const [currentDebateRoom, setCurrentDebateRoom] = useState<import('./AgentDebateStream').DebateRoomStateData | null>(null);
  const [isExternalLaneOpen, setIsExternalLaneOpen] = useState(false);
  const [currentLaneConfig, setCurrentLaneConfig] = useState<import('./ExternalAgentProcessLane').ExternalAgentConfigData | null>(null);
  const [currentLaneReceipts, setCurrentLaneReceipts] = useState<import('./ExternalAgentProcessLane').ProcessReceiptData[]>([]);
  const [isTradeoffMatrixOpen, setIsTradeoffMatrixOpen] = useState(false);
  const [currentTradeoffMatrix, setCurrentTradeoffMatrix] = useState<import('./DebateTradeoffMatrixCard').TradeoffMatrixData | null>(null);
  const [isTeamSupervisionOpen, setIsTeamSupervisionOpen] = useState(false);
  const [currentTeamProjection, setCurrentTeamProjection] = useState<import('./LiveTeamSupervisionKanban').TeamProjectionData | null>(null);

  useEffect(() => {
    const handleOpenTeams = (e: Event) => {
      const customEvent = e as CustomEvent<import('./LiveTeamSupervisionKanban').TeamProjectionData>;
      if (customEvent.detail) {
        setCurrentTeamProjection(customEvent.detail);
      }
      setIsTeamSupervisionOpen(true);
    };
    const handleCloseTeams = () => setIsTeamSupervisionOpen(false);
    window.addEventListener('myrm:open-team-supervision', handleOpenTeams);
    window.addEventListener('myrm:close-team-supervision', handleCloseTeams);
    return () => {
      window.removeEventListener('myrm:open-team-supervision', handleOpenTeams);
      window.removeEventListener('myrm:close-team-supervision', handleCloseTeams);
    };
  }, []);

  const [isFailurePolicyOpen, setIsFailurePolicyOpen] = useState(false);
  const [currentFailurePolicyDecision, setCurrentFailurePolicyDecision] = useState<import('./SubagentFailurePolicyCard').RemediationDecisionItem | null>(null);
  const [currentFailurePolicyItem, setCurrentFailurePolicyItem] = useState<import('./SubagentFailurePolicyCard').RolePolicyItem | undefined>(undefined);

  useEffect(() => {
    const handleOpenFailurePolicy = (e: Event) => {
      const customEvent = e as CustomEvent<{
        decision?: import('./SubagentFailurePolicyCard').RemediationDecisionItem;
        policy?: import('./SubagentFailurePolicyCard').RolePolicyItem;
      }>;
      if (customEvent.detail?.decision) {
        setCurrentFailurePolicyDecision(customEvent.detail.decision);
      }
      if (customEvent.detail?.policy) {
        setCurrentFailurePolicyItem(customEvent.detail.policy);
      }
      setIsFailurePolicyOpen(true);
    };
    const handleCloseFailurePolicy = () => setIsFailurePolicyOpen(false);
    window.addEventListener('myrm:open-failure-policy', handleOpenFailurePolicy);
    window.addEventListener('myrm:close-failure-policy', handleCloseFailurePolicy);
    return () => {
      window.removeEventListener('myrm:open-failure-policy', handleOpenFailurePolicy);
      window.removeEventListener('myrm:close-failure-policy', handleCloseFailurePolicy);
    };
  }, []);

  const [isWorkspaceBlueprintOpen, setIsWorkspaceBlueprintOpen] = useState(false);
  const [currentWorkspaceResolution, setCurrentWorkspaceResolution] = useState<import('./WorkspaceTeamBlueprintBar').WorkspaceBlueprintResolutionData | null>(null);

  useEffect(() => {
    const handleOpenWorkspaceBlueprint = (e: Event) => {
      const customEvent = e as CustomEvent<import('./WorkspaceTeamBlueprintBar').WorkspaceBlueprintResolutionData>;
      if (customEvent.detail) {
        setCurrentWorkspaceResolution(customEvent.detail);
      }
      setIsWorkspaceBlueprintOpen(true);
    };
    const handleCloseWorkspaceBlueprint = () => setIsWorkspaceBlueprintOpen(false);
    window.addEventListener('myrm:open-workspace-blueprint', handleOpenWorkspaceBlueprint);
    window.addEventListener('myrm:close-workspace-blueprint', handleCloseWorkspaceBlueprint);
    return () => {
      window.removeEventListener('myrm:open-workspace-blueprint', handleOpenWorkspaceBlueprint);
      window.removeEventListener('myrm:close-workspace-blueprint', handleCloseWorkspaceBlueprint);
    };
  }, []);

  const [isScopeGuardrailsOpen, setIsScopeGuardrailsOpen] = useState(false);
  const [currentScopeAudit, setCurrentScopeAudit] = useState<import('./SafeTeamDesignGuardrailsCard').TeamScopeAuditData | null>(null);

  useEffect(() => {
    const handleOpenScopeGuardrails = (e: Event) => {
      const customEvent = e as CustomEvent<import('./SafeTeamDesignGuardrailsCard').TeamScopeAuditData>;
      if (customEvent.detail) {
        setCurrentScopeAudit(customEvent.detail);
      }
      setIsScopeGuardrailsOpen(true);
    };
    const handleCloseScopeGuardrails = () => setIsScopeGuardrailsOpen(false);
    window.addEventListener('myrm:open-scope-guardrails', handleOpenScopeGuardrails);
    window.addEventListener('myrm:close-scope-guardrails', handleCloseScopeGuardrails);
    return () => {
      window.removeEventListener('myrm:open-scope-guardrails', handleOpenScopeGuardrails);
      window.removeEventListener('myrm:close-scope-guardrails', handleCloseScopeGuardrails);
    };
  }, []);

  const [isAutonomousLoopOpen, setIsAutonomousLoopOpen] = useState(false);
  const [currentAutonomousLoopState, setCurrentAutonomousLoopState] = useState<import('./AutonomousLoopModePill').AutonomousLoopStateData | null>(null);

  useEffect(() => {
    const handleOpenAutonomousLoop = (e: Event) => {
      const customEvent = e as CustomEvent<import('./AutonomousLoopModePill').AutonomousLoopStateData>;
      if (customEvent.detail) {
        setCurrentAutonomousLoopState(customEvent.detail);
      }
      setIsAutonomousLoopOpen(true);
    };
    const handleCloseAutonomousLoop = () => setIsAutonomousLoopOpen(false);
    window.addEventListener('myrm:open-autonomous-loop', handleOpenAutonomousLoop);
    window.addEventListener('myrm:close-autonomous-loop', handleCloseAutonomousLoop);
    return () => {
      window.removeEventListener('myrm:open-autonomous-loop', handleOpenAutonomousLoop);
      window.removeEventListener('myrm:close-autonomous-loop', handleCloseAutonomousLoop);
    };
  }, []);

  const [isCreatorModeOpen, setIsCreatorModeOpen] = useState(false);
  const [currentCreatorModeDraft, setCurrentCreatorModeDraft] = useState<import('./CreatorModeStudioModal').AgentPresetDraftData | null>(null);

  useEffect(() => {
    const handleOpenCreatorMode = (e: Event) => {
      const customEvent = e as CustomEvent<import('./CreatorModeStudioModal').AgentPresetDraftData | null>;
      setCurrentCreatorModeDraft(customEvent.detail || null);
      setIsCreatorModeOpen(true);
    };
    const handleCloseCreatorMode = () => setIsCreatorModeOpen(false);
    window.addEventListener('myrm:open-creator-mode', handleOpenCreatorMode);
    window.addEventListener('myrm:close-creator-mode', handleCloseCreatorMode);
    return () => {
      window.removeEventListener('myrm:open-creator-mode', handleOpenCreatorMode);
      window.removeEventListener('myrm:close-creator-mode', handleCloseCreatorMode);
    };
  }, []);

  const [isTriRoleOpen, setIsTriRoleOpen] = useState(false);
  const [currentTriRoleSession, setCurrentTriRoleSession] = useState<import('./TriRolePipelinePanel').TriRoleSessionData | null>(null);

  useEffect(() => {
    const handleOpenTriRole = (e: Event) => {
      const customEvent = e as CustomEvent<import('./TriRolePipelinePanel').TriRoleSessionData | null>;
      if (customEvent.detail) {
        setCurrentTriRoleSession(customEvent.detail);
      }
      setIsTriRoleOpen(true);
    };
    const handleCloseTriRole = () => {
      setIsTriRoleOpen(false);
    };
    window.addEventListener('myrm:open-tri-role', handleOpenTriRole);
    window.addEventListener('myrm:close-tri-role', handleCloseTriRole);
    return () => {
      window.removeEventListener('myrm:open-tri-role', handleOpenTriRole);
      window.removeEventListener('myrm:close-tri-role', handleCloseTriRole);
    };
  }, []);

  const [isSkillBundleModalOpen, setIsSkillBundleModalOpen] = useState(false);

  useEffect(() => {
    const handleOpenSkillBundles = () => {
      setIsSkillBundleModalOpen(true);
    };
    const handleCloseSkillBundles = () => {
      setIsSkillBundleModalOpen(false);
    };
    window.addEventListener('myrm:open-skill-bundles', handleOpenSkillBundles);
    window.addEventListener('myrm:close-skill-bundles', handleCloseSkillBundles);
    return () => {
      window.removeEventListener('myrm:open-skill-bundles', handleOpenSkillBundles);
      window.removeEventListener('myrm:close-skill-bundles', handleCloseSkillBundles);
    };
  }, []);

  const [isMultiBotFocusOpen, setIsMultiBotFocusOpen] = useState(false);

  useEffect(() => {
    const handleOpenMultiBotFocus = () => {
      setIsMultiBotFocusOpen(true);
    };
    const handleCloseMultiBotFocus = () => {
      setIsMultiBotFocusOpen(false);
    };
    window.addEventListener('myrm:open-multi-bot-focus', handleOpenMultiBotFocus);
    window.addEventListener('myrm:close-multi-bot-focus', handleCloseMultiBotFocus);
    return () => {
      window.removeEventListener('myrm:open-multi-bot-focus', handleOpenMultiBotFocus);
      window.removeEventListener('myrm:close-multi-bot-focus', handleCloseMultiBotFocus);
    };
  }, []);

  const [isMcpSummarizerOpen, setIsMcpSummarizerOpen] = useState(false);

  useEffect(() => {
    const handleOpenMcpSummarizer = () => {
      setIsMcpSummarizerOpen(true);
    };
    const handleCloseMcpSummarizer = () => {
      setIsMcpSummarizerOpen(false);
    };
    window.addEventListener('myrm:open-mcp-summarizer', handleOpenMcpSummarizer);
    window.addEventListener('myrm:close-mcp-summarizer', handleCloseMcpSummarizer);
    return () => {
      window.removeEventListener('myrm:open-mcp-summarizer', handleOpenMcpSummarizer);
      window.removeEventListener('myrm:close-mcp-summarizer', handleCloseMcpSummarizer);
    };
  }, []);

  const [isCodingWaveOpen, setIsCodingWaveOpen] = useState(false);

  useEffect(() => {
    const handleOpenCodingWave = () => {
      setIsCodingWaveOpen(true);
    };
    const handleCloseCodingWave = () => {
      setIsCodingWaveOpen(false);
    };
    window.addEventListener('myrm:open-coding-wave', handleOpenCodingWave);
    window.addEventListener('myrm:close-coding-wave', handleCloseCodingWave);
    return () => {
      window.removeEventListener('myrm:open-coding-wave', handleOpenCodingWave);
      window.removeEventListener('myrm:close-coding-wave', handleCloseCodingWave);
    };
  }, []);

  const [isSubagentLifecycleOpen, setIsSubagentLifecycleOpen] = useState(false);

  useEffect(() => {
    const handleOpenSubagentLifecycle = () => {
      setIsSubagentLifecycleOpen(true);
    };
    const handleCloseSubagentLifecycle = () => {
      setIsSubagentLifecycleOpen(false);
    };
    window.addEventListener('myrm:open-subagent-lifecycle', handleOpenSubagentLifecycle);
    window.addEventListener('myrm:close-subagent-lifecycle', handleCloseSubagentLifecycle);
    return () => {
      window.removeEventListener('myrm:open-subagent-lifecycle', handleOpenSubagentLifecycle);
      window.removeEventListener('myrm:close-subagent-lifecycle', handleCloseSubagentLifecycle);
    };
  }, []);

  const [isMixedFleetOpen, setIsMixedFleetOpen] = useState(false);

  useEffect(() => {
    const handleOpenMixedFleet = () => {
      setIsMixedFleetOpen(true);
    };
    const handleCloseMixedFleet = () => {
      setIsMixedFleetOpen(false);
    };
    window.addEventListener('myrm:open-mixed-fleet', handleOpenMixedFleet);
    window.addEventListener('myrm:close-mixed-fleet', handleCloseMixedFleet);
    return () => {
      window.removeEventListener('myrm:open-mixed-fleet', handleOpenMixedFleet);
      window.removeEventListener('myrm:close-mixed-fleet', handleCloseMixedFleet);
    };
  }, []);

  const [isZeroTokenContractOpen, setIsZeroTokenContractOpen] = useState(false);

  useEffect(() => {
    const handleOpenZeroToken = () => {
      setIsZeroTokenContractOpen(true);
    };
    const handleCloseZeroToken = () => {
      setIsZeroTokenContractOpen(false);
    };
    window.addEventListener('myrm:open-zero-token-contract', handleOpenZeroToken);
    window.addEventListener('myrm:close-zero-token-contract', handleCloseZeroToken);
    return () => {
      window.removeEventListener('myrm:open-zero-token-contract', handleOpenZeroToken);
      window.removeEventListener('myrm:close-zero-token-contract', handleCloseZeroToken);
    };
  }, []);

  const [isCrossSurfaceBridgeOpen, setIsCrossSurfaceBridgeOpen] = useState(false);

  useEffect(() => {
    const handleOpenBridge = () => {
      setIsCrossSurfaceBridgeOpen(true);
    };
    const handleCloseBridge = () => {
      setIsCrossSurfaceBridgeOpen(false);
    };
    window.addEventListener('myrm:open-cross-surface-bridge', handleOpenBridge);
    window.addEventListener('myrm:close-cross-surface-bridge', handleCloseBridge);
    return () => {
      window.removeEventListener('myrm:open-cross-surface-bridge', handleOpenBridge);
      window.removeEventListener('myrm:close-cross-surface-bridge', handleCloseBridge);
    };
  }, []);

  const [isMultiLaneOpen, setIsMultiLaneOpen] = useState(false);

  useEffect(() => {
    const handleOpenMultiLane = () => {
      setIsMultiLaneOpen(true);
    };
    const handleCloseMultiLane = () => {
      setIsMultiLaneOpen(false);
    };
    window.addEventListener('myrm:open-multi-lane', handleOpenMultiLane);
    window.addEventListener('myrm:close-multi-lane', handleCloseMultiLane);
    return () => {
      window.removeEventListener('myrm:open-multi-lane', handleOpenMultiLane);
      window.removeEventListener('myrm:close-multi-lane', handleCloseMultiLane);
    };
  }, []);

  const [isSessionForkOpen, setIsSessionForkOpen] = useState(false);

  useEffect(() => {
    const handleOpenSessionFork = () => {
      setIsSessionForkOpen(true);
    };
    const handleCloseSessionFork = () => {
      setIsSessionForkOpen(false);
    };
    window.addEventListener('myrm:open-session-fork', handleOpenSessionFork);
    window.addEventListener('myrm:close-session-fork', handleCloseSessionFork);
    return () => {
      window.removeEventListener('myrm:open-session-fork', handleOpenSessionFork);
      window.removeEventListener('myrm:close-session-fork', handleCloseSessionFork);
    };
  }, []);

  const [isTokenGovernanceOpen, setIsTokenGovernanceOpen] = useState(false);

  useEffect(() => {
    const handleOpenTokenGov = () => {
      setIsTokenGovernanceOpen(true);
    };
    const handleCloseTokenGov = () => {
      setIsTokenGovernanceOpen(false);
    };
    window.addEventListener('myrm:open-token-governance', handleOpenTokenGov);
    window.addEventListener('myrm:close-token-governance', handleCloseTokenGov);
    return () => {
      window.removeEventListener('myrm:open-token-governance', handleOpenTokenGov);
      window.removeEventListener('myrm:close-token-governance', handleCloseTokenGov);
    };
  }, []);

  const [isPipelineIntegrityOpen, setIsPipelineIntegrityOpen] = useState(false);

  useEffect(() => {
    const handleOpenIntegrity = () => {
      setIsPipelineIntegrityOpen(true);
    };
    const handleCloseIntegrity = () => {
      setIsPipelineIntegrityOpen(false);
    };
    window.addEventListener('myrm:open-pipeline-integrity', handleOpenIntegrity);
    window.addEventListener('myrm:close-pipeline-integrity', handleCloseIntegrity);
    return () => {
      window.removeEventListener('myrm:open-pipeline-integrity', handleOpenIntegrity);
      window.removeEventListener('myrm:close-pipeline-integrity', handleCloseIntegrity);
    };
  }, []);

  const [isSpecialistSummoningOpen, setIsSpecialistSummoningOpen] = useState(false);

  useEffect(() => {
    const handleOpenSummoning = () => {
      setIsSpecialistSummoningOpen(true);
    };
    const handleCloseSummoning = () => {
      setIsSpecialistSummoningOpen(false);
    };
    window.addEventListener('myrm:open-specialist-summoning', handleOpenSummoning);
    window.addEventListener('myrm:close-specialist-summoning', handleCloseSummoning);
    return () => {
      window.removeEventListener('myrm:open-specialist-summoning', handleOpenSummoning);
      window.removeEventListener('myrm:close-specialist-summoning', handleCloseSummoning);
    };
  }, []);

  const [isSwarmTopologyMeshOpen, setIsSwarmTopologyMeshOpen] = useState(false);

  useEffect(() => {
    const handleOpenSwarmMesh = () => {
      setIsSwarmTopologyMeshOpen(true);
    };
    const handleCloseSwarmMesh = () => {
      setIsSwarmTopologyMeshOpen(false);
    };
    window.addEventListener('myrm:open-swarm-mesh', handleOpenSwarmMesh);
    window.addEventListener('myrm:close-swarm-mesh', handleCloseSwarmMesh);
    return () => {
      window.removeEventListener('myrm:open-swarm-mesh', handleOpenSwarmMesh);
      window.removeEventListener('myrm:close-swarm-mesh', handleCloseSwarmMesh);
    };
  }, []);

  const [isWorkspaceInheritanceOpen, setIsWorkspaceInheritanceOpen] = useState(false);

  useEffect(() => {
    const handleOpenWorkspaceInheritance = () => {
      setIsWorkspaceInheritanceOpen(true);
    };
    const handleCloseWorkspaceInheritance = () => {
      setIsWorkspaceInheritanceOpen(false);
    };
    window.addEventListener('myrm:open-workspace-inheritance', handleOpenWorkspaceInheritance);
    window.addEventListener('myrm:close-workspace-inheritance', handleCloseWorkspaceInheritance);
    return () => {
      window.removeEventListener('myrm:open-workspace-inheritance', handleOpenWorkspaceInheritance);
      window.removeEventListener('myrm:close-workspace-inheritance', handleCloseWorkspaceInheritance);
    };
  }, []);

  const [isReplayDedupHarmonizerOpen, setIsReplayDedupHarmonizerOpen] = useState(false);

  useEffect(() => {
    const handleOpenReplayDedup = () => {
      setIsReplayDedupHarmonizerOpen(true);
    };
    const handleCloseReplayDedup = () => {
      setIsReplayDedupHarmonizerOpen(false);
    };
    window.addEventListener('myrm:open-replay-dedup-harmonizer', handleOpenReplayDedup);
    window.addEventListener('myrm:close-replay-dedup-harmonizer', handleCloseReplayDedup);
    return () => {
      window.removeEventListener('myrm:open-replay-dedup-harmonizer', handleOpenReplayDedup);
      window.removeEventListener('myrm:close-replay-dedup-harmonizer', handleCloseReplayDedup);
    };
  }, []);

  const [isCloudEdgeRelayOpen, setIsCloudEdgeRelayOpen] = useState(false);

  useEffect(() => {
    const handleOpenCloudEdgeRelay = () => {
      setIsCloudEdgeRelayOpen(true);
    };
    const handleCloseCloudEdgeRelay = () => {
      setIsCloudEdgeRelayOpen(false);
    };
    window.addEventListener('myrm:open-cloud-edge-relay', handleOpenCloudEdgeRelay);
    window.addEventListener('myrm:close-cloud-edge-relay', handleCloseCloudEdgeRelay);
    return () => {
      window.removeEventListener('myrm:open-cloud-edge-relay', handleOpenCloudEdgeRelay);
      window.removeEventListener('myrm:close-cloud-edge-relay', handleCloseCloudEdgeRelay);
    };
  }, []);

  const [isVirtualRoomOpen, setIsVirtualRoomOpen] = useState(false);

  useEffect(() => {
    const handleOpenVirtualRoom = () => {
      setIsVirtualRoomOpen(true);
    };
    const handleCloseVirtualRoom = () => {
      setIsVirtualRoomOpen(false);
    };
    window.addEventListener('myrm:open-virtual-room', handleOpenVirtualRoom);
    window.addEventListener('myrm:close-virtual-room', handleCloseVirtualRoom);
    return () => {
      window.removeEventListener('myrm:open-virtual-room', handleOpenVirtualRoom);
      window.removeEventListener('myrm:close-virtual-room', handleCloseVirtualRoom);
    };
  }, []);

  const [isSwarmOffloadOpen, setIsSwarmOffloadOpen] = useState(false);
  const [isVisualTimelineOpen, setIsVisualTimelineOpen] = useState(false);
  const [isCleanCodePipelineOpen, setIsCleanCodePipelineOpen] = useState(false);
  const [isFusenBoardOpen, setIsFusenBoardOpen] = useState(false);

  useEffect(() => {
    const handleOpenSwarmOffload = () => {
      setIsSwarmOffloadOpen(true);
    };
    const handleCloseSwarmOffload = () => {
      setIsSwarmOffloadOpen(false);
    };
    window.addEventListener('myrm:open-swarm-offload', handleOpenSwarmOffload);
    window.addEventListener('myrm:close-swarm-offload', handleCloseSwarmOffload);
    return () => {
      window.removeEventListener('myrm:open-swarm-offload', handleOpenSwarmOffload);
      window.removeEventListener('myrm:close-swarm-offload', handleCloseSwarmOffload);
    };
  }, []);

  useEffect(() => {
    const handleOpenVisualTimeline = () => {
      setIsVisualTimelineOpen(true);
    };
    const handleCloseVisualTimeline = () => {
      setIsVisualTimelineOpen(false);
    };
    window.addEventListener('myrm:open-visual-timeline', handleOpenVisualTimeline);
    window.addEventListener('myrm:close-visual-timeline', handleCloseVisualTimeline);
    return () => {
      window.removeEventListener('myrm:open-visual-timeline', handleOpenVisualTimeline);
      window.removeEventListener('myrm:close-visual-timeline', handleCloseVisualTimeline);
    };
  }, []);

  useEffect(() => {
    const handleOpenCleanCodePipeline = () => {
      setIsCleanCodePipelineOpen(true);
    };
    const handleCloseCleanCodePipeline = () => {
      setIsCleanCodePipelineOpen(false);
    };
    window.addEventListener('myrm:open-clean-code-pipeline', handleOpenCleanCodePipeline);
    window.addEventListener('myrm:close-clean-code-pipeline', handleCloseCleanCodePipeline);
    return () => {
      window.removeEventListener('myrm:open-clean-code-pipeline', handleOpenCleanCodePipeline);
      window.removeEventListener('myrm:close-clean-code-pipeline', handleCloseCleanCodePipeline);
    };
  }, []);

  useEffect(() => {
    const handleOpenFusenBoard = () => {
      setIsFusenBoardOpen(true);
    };
    const handleCloseFusenBoard = () => {
      setIsFusenBoardOpen(false);
    };
    window.addEventListener('myrm:open-fusen-board', handleOpenFusenBoard);
    window.addEventListener('myrm:close-fusen-board', handleCloseFusenBoard);
    return () => {
      window.removeEventListener('myrm:open-fusen-board', handleOpenFusenBoard);
      window.removeEventListener('myrm:close-fusen-board', handleCloseFusenBoard);
    };
  }, []);



  useEffect(() => {
    const handleOpen = () => setIsContextInspectorOpen(true);
    window.addEventListener('myrm:open-context-inspector', handleOpen);
    return () => {
      window.removeEventListener('myrm:open-context-inspector', handleOpen);
    };
  }, []);

  useEffect(() => {
    const handleOpenFifo = () => setIsReportFifoOpen(true);
    const handleCloseFifo = () => setIsReportFifoOpen(false);
    window.addEventListener('myrm:open-report-fifo', handleOpenFifo);
    window.addEventListener('myrm:close-report-fifo', handleCloseFifo);
    return () => {
      window.removeEventListener('myrm:open-report-fifo', handleOpenFifo);
      window.removeEventListener('myrm:close-report-fifo', handleCloseFifo);
    };
  }, []);

  useEffect(() => {
    const handleOpenFacts = (e: Event) => {
      const customEvent = e as CustomEvent<import('./SubagentFailureFactBanner').StructuredFailureFactItem>;
      if (customEvent.detail) {
        setCurrentFailureFact(customEvent.detail);
      }
      setIsFailureFactsOpen(true);
    };
    const handleCloseFacts = () => setIsFailureFactsOpen(false);
    window.addEventListener('myrm:open-failure-facts', handleOpenFacts);
    window.addEventListener('myrm:close-failure-facts', handleCloseFacts);
    return () => {
      window.removeEventListener('myrm:open-failure-facts', handleOpenFacts);
      window.removeEventListener('myrm:close-failure-facts', handleCloseFacts);
    };
  }, []);

  useEffect(() => {
    const handleOpenDebate = (e: Event) => {
      const customEvent = e as CustomEvent<import('./AgentDebateStream').DebateRoomStateData>;
      if (customEvent.detail) {
        setCurrentDebateRoom(customEvent.detail);
      }
      setIsDebateStreamOpen(true);
    };
    const handleCloseDebate = () => setIsDebateStreamOpen(false);
    window.addEventListener('myrm:open-debate-stream', handleOpenDebate);
    window.addEventListener('myrm:close-debate-stream', handleCloseDebate);
    return () => {
      window.removeEventListener('myrm:open-debate-stream', handleOpenDebate);
      window.removeEventListener('myrm:close-debate-stream', handleCloseDebate);
    };
  }, []);

  useEffect(() => {
    const handleOpenLane = (e: Event) => {
      const customEvent = e as CustomEvent<{
        config: import('./ExternalAgentProcessLane').ExternalAgentConfigData;
        receipts?: import('./ExternalAgentProcessLane').ProcessReceiptData[];
      }>;
      if (customEvent.detail?.config) {
        setCurrentLaneConfig(customEvent.detail.config);
        setCurrentLaneReceipts(customEvent.detail.receipts || []);
      }
      setIsExternalLaneOpen(true);
    };
    const handleCloseLane = () => setIsExternalLaneOpen(false);
    window.addEventListener('myrm:open-external-cli-lane', handleOpenLane);
    window.addEventListener('myrm:close-external-cli-lane', handleCloseLane);
    return () => {
      window.removeEventListener('myrm:open-external-cli-lane', handleOpenLane);
      window.removeEventListener('myrm:close-external-cli-lane', handleCloseLane);
    };
  }, []);

  useEffect(() => {
    const handleOpenMatrix = (e: Event) => {
      const customEvent = e as CustomEvent<import('./DebateTradeoffMatrixCard').TradeoffMatrixData>;
      if (customEvent.detail) {
        setCurrentTradeoffMatrix(customEvent.detail);
      }
      setIsTradeoffMatrixOpen(true);
    };
    const handleCloseMatrix = () => setIsTradeoffMatrixOpen(false);
    window.addEventListener('myrm:open-tradeoff-matrix', handleOpenMatrix);
    window.addEventListener('myrm:close-tradeoff-matrix', handleCloseMatrix);
    return () => {
      window.removeEventListener('myrm:open-tradeoff-matrix', handleOpenMatrix);
      window.removeEventListener('myrm:close-tradeoff-matrix', handleCloseMatrix);
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

  const isDeviceInspectorOpen = useDeviceInspectorStore((s) => s.isOpen);
  const closeDeviceInspector = useDeviceInspectorStore((s) => s.closePanel);
  useClosePanelOnChatSwitch(effectiveChatId, isDeviceInspectorOpen, closeDeviceInspector);

  const isUiAlignmentOpen = useUiAlignmentStore((s) => s.isOpen);
  const setUiAlignmentOpen = useUiAlignmentStore((s) => s.setOpen);

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
      <TaskSpaceDock />
      <DesktopInspectorToggle />
      <DesktopLiveView onSendInstruction={onDesktopInspectorInstruction} />
      <DeviceInspectorToggle />
      <DeviceLiveView onSendInstruction={onDesktopInspectorInstruction} />
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
      <ContextFootprintInspector
        open={isContextInspectorOpen}
        onClose={() => setIsContextInspectorOpen(false)}
      />
      <TaskExecutionTimelineDrawer />
      {chatId ? (
        <div className="fixed top-3.5 right-28 z-40 max-sm:hidden">
          <ReconnectStatusPill sessionId={chatId} />
        </div>
      ) : null}
      <CommandMatrixModal />
      {effectiveChatId && isUiAlignmentOpen ? (
        <UiVariantCompareViewer
          chatId={effectiveChatId}
          isOpen={isUiAlignmentOpen}
          onClose={() => setUiAlignmentOpen(false)}
        />
      ) : null}
      <DelightTemplateGalleryModal />
      <SingleFileSandboxShowcase />
      {effectiveChatId && isGeneratorModalOpen ? (
        <WidgetGeneratorModal
          chatId={effectiveChatId}
          isOpen={isGeneratorModalOpen}
          onClose={() => setGeneratorModalOpen(false)}
        />
      ) : null}
      {effectiveChatId && isReportFifoOpen ? (
        <div className="fixed top-16 right-6 z-50 max-w-md w-full animate-in fade-in slide-in-from-top-2">
          <OrderedReportSettlementFeed
            chatId={effectiveChatId}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isFailureFactsOpen && currentFailureFact ? (
        <div className="fixed top-20 right-6 z-50 max-w-lg w-full animate-in fade-in slide-in-from-top-2">
          <SubagentFailureFactBanner
            chatId={effectiveChatId}
            fact={currentFailureFact}
            onDismiss={() => setIsFailureFactsOpen(false)}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isDebateStreamOpen && currentDebateRoom ? (
        <div className="fixed top-20 right-6 z-50 max-w-xl w-full animate-in fade-in slide-in-from-top-2">
          <AgentDebateStream
            room={currentDebateRoom}
            onDismiss={() => setIsDebateStreamOpen(false)}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isExternalLaneOpen && currentLaneConfig ? (
        <div className="fixed top-20 right-6 z-50 max-w-xl w-full animate-in fade-in slide-in-from-top-2">
          <ExternalAgentProcessLane
            config={currentLaneConfig}
            receipts={currentLaneReceipts}
            onDismiss={() => setIsExternalLaneOpen(false)}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isTradeoffMatrixOpen && currentTradeoffMatrix ? (
        <div className="fixed top-20 right-6 z-50 max-w-xl w-full animate-in fade-in slide-in-from-top-2">
          <DebateTradeoffMatrixCard
            matrix={currentTradeoffMatrix}
            onDismiss={() => setIsTradeoffMatrixOpen(false)}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isTeamSupervisionOpen && currentTeamProjection ? (
        <div className="fixed top-20 right-6 z-50 max-w-4xl w-full animate-in fade-in slide-in-from-top-2">
          <LiveTeamSupervisionKanban
            projection={currentTeamProjection}
            onDismiss={() => setIsTeamSupervisionOpen(false)}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isFailurePolicyOpen ? (
        <div className="fixed top-20 right-6 z-50 max-w-lg w-full animate-in fade-in slide-in-from-top-2">
          <SubagentFailurePolicyCard
            chatId={effectiveChatId}
            policy={currentFailurePolicyItem}
            latestDecision={currentFailurePolicyDecision}
            onDismiss={() => setIsFailurePolicyOpen(false)}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isWorkspaceBlueprintOpen ? (
        <div className="fixed top-20 right-6 z-50 max-w-xl w-full animate-in fade-in slide-in-from-top-2">
          <WorkspaceTeamBlueprintBar
            workspaceId={effectiveChatId}
            resolution={currentWorkspaceResolution}
            onDismiss={() => setIsWorkspaceBlueprintOpen(false)}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isScopeGuardrailsOpen && currentScopeAudit ? (
        <div className="fixed top-20 right-6 z-50 max-w-lg w-full animate-in fade-in slide-in-from-top-2">
          <SafeTeamDesignGuardrailsCard
            chatId={effectiveChatId}
            audit={currentScopeAudit}
            onDismiss={() => setIsScopeGuardrailsOpen(false)}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isAutonomousLoopOpen && currentAutonomousLoopState ? (
        <div className="fixed top-20 right-6 z-50 max-w-md w-full animate-in fade-in slide-in-from-top-2">
          <AutonomousLoopModePill
            chatId={effectiveChatId}
            loopState={currentAutonomousLoopState}
            onDismiss={() => setIsAutonomousLoopOpen(false)}
            className="shadow-xl"
          />
        </div>
      ) : null}
      {effectiveChatId && isCreatorModeOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="max-w-2xl w-full">
            <CreatorModeStudioModal
              chatId={effectiveChatId}
              initialDraft={currentCreatorModeDraft}
              onDismiss={() => setIsCreatorModeOpen(false)}
            />
          </div>
        </div>
      ) : null}
      {effectiveChatId && isTriRoleOpen && currentTriRoleSession ? (
        <div className="fixed bottom-20 right-6 z-40 max-w-xl w-full">
          <TriRolePipelinePanel
            session={currentTriRoleSession}
            onClose={() => {
              setIsTriRoleOpen(false);
            }}
          />
        </div>
      ) : null}
      {effectiveChatId && isSkillBundleModalOpen ? (
        <SkillBundleWarmupModal
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsSkillBundleModalOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isMultiBotFocusOpen ? (
        <MultiBotFocusIndicator
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsMultiBotFocusOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isMcpSummarizerOpen ? (
        <McpPayloadSummarizerCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsMcpSummarizerOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isCodingWaveOpen ? (
        <CodingWavePresetModal
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsCodingWaveOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isSubagentLifecycleOpen ? (
        <SubagentLifecycleToolchainCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsSubagentLifecycleOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isMixedFleetOpen ? (
        <MixedFleetPresetCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsMixedFleetOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isZeroTokenContractOpen ? (
        <ZeroTokenContractCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsZeroTokenContractOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isCrossSurfaceBridgeOpen ? (
        <CrossSurfaceActivityBridgeCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsCrossSurfaceBridgeOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isMultiLaneOpen ? (
        <MultiLaneParallelExecutionCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsMultiLaneOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isSessionForkOpen ? (
        <DeterministicSessionForkCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsSessionForkOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isTokenGovernanceOpen ? (
        <SharedTokenBudgetGovernanceCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsTokenGovernanceOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isPipelineIntegrityOpen ? (
        <PipelineIntegrityDoctorCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsPipelineIntegrityOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isSpecialistSummoningOpen ? (
        <ConversationalSpecialistSummoningCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsSpecialistSummoningOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isSwarmTopologyMeshOpen ? (
        <SwarmTopologyMeshCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsSwarmTopologyMeshOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isWorkspaceInheritanceOpen ? (
        <SubagentWorkspaceInheritanceCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsWorkspaceInheritanceOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isReplayDedupHarmonizerOpen ? (
        <SubagentReplayDedupHarmonizerCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsReplayDedupHarmonizerOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isCloudEdgeRelayOpen ? (
        <SubagentCloudEdgeRelayCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsCloudEdgeRelayOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isVirtualRoomOpen ? (
        <VirtualRoomCoDevCockpitCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsVirtualRoomOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isSwarmOffloadOpen ? (
        <HighConcurrencySwarmOffloadCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsSwarmOffloadOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isVisualTimelineOpen ? (
        <VisualTimelineCherryPickCard
          chatId={effectiveChatId}
          onDismiss={() => {
            setIsVisualTimelineOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isCleanCodePipelineOpen ? (
        <CleanCodeAssemblyPipelineCard
          sessionId={effectiveChatId}
          onDismiss={() => {
            setIsCleanCodePipelineOpen(false);
          }}
        />
      ) : null}
      {effectiveChatId && isFusenBoardOpen ? (
        <LightweightFusenBoardCard
          sessionId={effectiveChatId}
          onDismiss={() => {
            setIsFusenBoardOpen(false);
          }}
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

export const ExportedOrderedReportSettlementFeed = dynamic(
  () => import('./OrderedReportSettlementFeed').then((module) => ({ default: module.OrderedReportSettlementFeed })),
  { ssr: false },
);

export const ExportedSubagentFailureFactBanner = dynamic(
  () => import('./SubagentFailureFactBanner').then((module) => ({ default: module.SubagentFailureFactBanner })),
  { ssr: false },
);

export const ExportedAgentDebateStream = dynamic(
  () => import('./AgentDebateStream').then((module) => ({ default: module.AgentDebateStream })),
  { ssr: false },
);

export const ExportedExternalAgentProcessLane = dynamic(
  () => import('./ExternalAgentProcessLane').then((module) => ({ default: module.ExternalAgentProcessLane })),
  { ssr: false },
);

export const ExportedDebateTradeoffMatrixCard = dynamic(
  () => import('./DebateTradeoffMatrixCard').then((module) => ({ default: module.DebateTradeoffMatrixCard })),
  { ssr: false },
);

export const ExportedLiveTeamSupervisionKanban = dynamic(
  () => import('./LiveTeamSupervisionKanban').then((module) => ({ default: module.LiveTeamSupervisionKanban })),
  { ssr: false },
);

export const ExportedAdaptiveWakeupIndicator = dynamic(
  () => import('./AdaptiveWakeupIndicator').then((module) => ({ default: module.AdaptiveWakeupIndicator })),
  { ssr: false },
);

export const ExportedSubagentWatermarkAlertChip = dynamic(
  () => import('./SubagentWatermarkAlertChip').then((module) => ({ default: module.SubagentWatermarkAlertChip })),
  { ssr: false },
);

export const ExportedReviewLoopDashboard = dynamic(
  () => import('./ReviewLoopDashboard').then((module) => ({ default: module.ReviewLoopDashboard })),
  { ssr: false },
);

export const ExportedBotTeamRosterMailbox = dynamic(
  () => import('./BotTeamRosterMailbox').then((module) => ({ default: module.BotTeamRosterMailbox })),
  { ssr: false },
);

export const ExportedSquadCompositionWizard = dynamic(
  () => import('./SquadCompositionWizard').then((module) => ({ default: module.SquadCompositionWizard })),
  { ssr: false },
);

export const ExportedSubagentFailurePolicyCard = dynamic(
  () => import('./SubagentFailurePolicyCard').then((module) => ({ default: module.SubagentFailurePolicyCard })),
  { ssr: false },
);

export const ExportedWorkspaceTeamBlueprintBar = dynamic(
  () => import('./WorkspaceTeamBlueprintBar').then((module) => ({ default: module.WorkspaceTeamBlueprintBar })),
  { ssr: false },
);

export const ExportedSafeTeamDesignGuardrailsCard = dynamic(
  () => import('./SafeTeamDesignGuardrailsCard').then((module) => ({ default: module.SafeTeamDesignGuardrailsCard })),
  { ssr: false },
);

export const ExportedAutonomousLoopModePill = dynamic(
  () => import('./AutonomousLoopModePill').then((module) => ({ default: module.AutonomousLoopModePill })),
  { ssr: false },
);

export const ExportedCreatorModeStudioModal = dynamic(
  () => import('./CreatorModeStudioModal').then((module) => ({ default: module.CreatorModeStudioModal })),
  { ssr: false },
);

export const ExportedTriRolePipelinePanel = dynamic(
  () => import('./TriRolePipelinePanel').then((module) => ({ default: module.TriRolePipelinePanel })),
  { ssr: false },
);

export const ExportedSkillBundleWarmupModal = dynamic(
  () => import('./SkillBundleWarmupModal').then((module) => ({ default: module.SkillBundleWarmupModal })),
  { ssr: false },
);

export const ExportedMultiBotFocusIndicator = dynamic(
  () => import('./MultiBotFocusIndicator').then((module) => ({ default: module.MultiBotFocusIndicator })),
  { ssr: false },
);

export const ExportedMcpPayloadSummarizerCard = dynamic(
  () => import('./McpPayloadSummarizerCard').then((module) => ({ default: module.McpPayloadSummarizerCard })),
  { ssr: false },
);

export const ExportedCodingWavePresetModal = dynamic(
  () => import('./CodingWavePresetModal').then((module) => ({ default: module.CodingWavePresetModal })),
  { ssr: false },
);

export const ExportedSubagentLifecycleToolchainCard = dynamic(
  () => import('./SubagentLifecycleToolchainCard').then((module) => ({ default: module.SubagentLifecycleToolchainCard })),
  { ssr: false },
);

export const ExportedMixedFleetPresetCard = dynamic(
  () => import('./MixedFleetPresetCard').then((module) => ({ default: module.MixedFleetPresetCard })),
  { ssr: false },
);

export const ExportedZeroTokenContractCard = dynamic(
  () => import('./ZeroTokenContractCard').then((module) => ({ default: module.ZeroTokenContractCard })),
  { ssr: false },
);

export const ExportedCrossSurfaceActivityBridgeCard = dynamic(
  () => import('./CrossSurfaceActivityBridgeCard').then((module) => ({ default: module.CrossSurfaceActivityBridgeCard })),
  { ssr: false },
);

export const ExportedMultiLaneParallelExecutionCard = dynamic(
  () => import('./MultiLaneParallelExecutionCard').then((module) => ({ default: module.MultiLaneParallelExecutionCard })),
  { ssr: false },
);

export const ExportedDeterministicSessionForkCard = dynamic(
  () => import('./DeterministicSessionForkCard').then((module) => ({ default: module.DeterministicSessionForkCard })),
  { ssr: false },
);

export const ExportedSharedTokenBudgetGovernanceCard = dynamic(
  () => import('./SharedTokenBudgetGovernanceCard').then((module) => ({ default: module.SharedTokenBudgetGovernanceCard })),
  { ssr: false },
);

export const ExportedPipelineIntegrityDoctorCard = dynamic(
  () => import('./PipelineIntegrityDoctorCard').then((module) => ({ default: module.PipelineIntegrityDoctorCard })),
  { ssr: false },
);

export const ExportedConversationalSpecialistSummoningCard = dynamic(
  () => import('./ConversationalSpecialistSummoningCard').then((module) => ({ default: module.ConversationalSpecialistSummoningCard })),
  { ssr: false },
);

export const ExportedSwarmTopologyMeshCard = dynamic(
  () => import('./SwarmTopologyMeshCard').then((module) => ({ default: module.SwarmTopologyMeshCard })),
  { ssr: false },
);

export const ExportedSubagentWorkspaceInheritanceCard = dynamic(
  () => import('./SubagentWorkspaceInheritanceCard').then((module) => ({ default: module.SubagentWorkspaceInheritanceCard })),
  { ssr: false },
);

export const ExportedSubagentReplayDedupHarmonizerCard = dynamic(
  () => import('./SubagentReplayDedupHarmonizerCard').then((module) => ({ default: module.SubagentReplayDedupHarmonizerCard })),
  { ssr: false },
);

export const ExportedSubagentCloudEdgeRelayCard = dynamic(
  () => import('./SubagentCloudEdgeRelayCard').then((module) => ({ default: module.SubagentCloudEdgeRelayCard })),
  { ssr: false },
);

export const ExportedVirtualRoomCoDevCockpitCard = dynamic(
  () => import('./VirtualRoomCoDevCockpitCard').then((module) => ({ default: module.VirtualRoomCoDevCockpitCard })),
  { ssr: false },
);

export const ExportedHighConcurrencySwarmOffloadCard = dynamic(
  () => import('./HighConcurrencySwarmOffloadCard').then((module) => ({ default: module.HighConcurrencySwarmOffloadCard })),
  { ssr: false },
);

export const ExportedVisualTimelineCherryPickCard = dynamic(
  () => import('./VisualTimelineCherryPickCard').then((module) => ({ default: module.VisualTimelineCherryPickCard })),
  { ssr: false },
);

export const ExportedCleanCodeAssemblyPipelineCard = dynamic(
  () => import('./CleanCodeAssemblyPipelineCard').then((module) => ({ default: module.CleanCodeAssemblyPipelineCard })),
  { ssr: false },
);

export const ExportedLightweightFusenBoardCard = dynamic(
  () => import('./LightweightFusenBoardCard').then((module) => ({ default: module.LightweightFusenBoardCard })),
  { ssr: false },
);

export const ExportedVerticalPresetsAndSandboxCard = dynamic(
  () => import('./VerticalPresetsAndSandboxCard').then((module) => ({ default: module.VerticalPresetsAndSandboxCard })),
  { ssr: false },
);

export const ExportedCouncilOfAgentsDeliberationCard = dynamic(
  () => import('./CouncilOfAgentsDeliberationCard').then((module) => ({ default: module.CouncilOfAgentsDeliberationCard })),
  { ssr: false },
);

export const ExportedVisualKanbanWorkflowDispatcherCard = dynamic(
  () => import('./VisualKanbanWorkflowDispatcherCard').then((module) => ({ default: module.VisualKanbanWorkflowDispatcherCard })),
  { ssr: false },
);

export const ExportedExternalCliSubagentPassthroughCard = dynamic(
  () => import('./ExternalCliSubagentPassthroughCard').then((module) => ({ default: module.ExternalCliSubagentPassthroughCard })),
  { ssr: false },
);

export const ExportedDagVisualOrchestratorCard = dynamic(
  () => import('./DagVisualOrchestratorCard').then((module) => ({ default: module.DagVisualOrchestratorCard })),
  { ssr: false },
);

export const ExportedPersistentKanbanJobQueueCard = dynamic(
  () => import('./PersistentKanbanJobQueueCard').then((module) => ({ default: module.PersistentKanbanJobQueueCard })),
  { ssr: false },
);

export const ExportedDiamondTopologyAuditorCard = dynamic(
  () => import('./DiamondTopologyAuditorCard').then((module) => ({ default: module.DiamondTopologyAuditorCard })),
  { ssr: false },
);

export const ExportedLiveDocumentCoAuthoringCard = dynamic(
  () => import('./LiveDocumentCoAuthoringCard').then((module) => ({ default: module.LiveDocumentCoAuthoringCard })),
  { ssr: false },
);

export const ExportedSocketMeshProtocolCard = dynamic(
  () => import('./SocketMeshProtocolCard').then((module) => ({ default: module.SocketMeshProtocolCard })),
  { ssr: false },
);

export const ExportedBotForgeStudioCard = dynamic(
  () => import('./BotForgeStudioCard').then((module) => ({ default: module.BotForgeStudioCard })),
  { ssr: false },
);

export const ExportedExternalAgentBundleManagerCard = dynamic(
  () => import('./ExternalAgentBundleManagerCard').then((module) => ({ default: module.ExternalAgentBundleManagerCard })),
  { ssr: false },
);

export const ExportedVisualMultiAgentKanbanCard = dynamic(
  () => import('./VisualMultiAgentKanbanCard').then((module) => ({ default: module.VisualMultiAgentKanbanCard })),
  { ssr: false },
);

export const ExportedFleetWideProfileRailCard = dynamic(
  () => import('./FleetWideProfileRailCard').then((module) => ({ default: module.FleetWideProfileRailCard })),
  { ssr: false },
);

export const ExportedGraphApplicabilityTriageCard = dynamic(
  () => import('./GraphApplicabilityTriageCard').then((module) => ({ default: module.GraphApplicabilityTriageCard })),
  { ssr: false },
);

















