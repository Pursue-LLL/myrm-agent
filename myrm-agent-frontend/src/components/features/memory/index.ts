// Memory 功能组件聚合门面。
// 组件按功能域收进子目录：cards / command-center / dialogs / guides /
// hooks / insights / pending / replay / settings / shared-context。
// 有 default 导出的组件在此重命名导出；纯命名导出的模块用 `export *` 透传。

// cards
export { default as MemoryCard } from './cards/MemoryCard';
export { default as ConflictCard } from './cards/ConflictCard';
export { default as MemoryDetailSheet } from './cards/MemoryDetailSheet';
export { default as MemoryTypeIcon } from './cards/MemoryTypeIcon';
export { default as MemoryStats } from './cards/MemoryStats';
export { default as PreferenceStabilityCard } from './cards/PreferenceStabilityCard';
export { default as TasteSummaryCard } from './cards/TasteSummaryCard';

// command-center
export { default as MemoryCommandCenter } from './command-center/MemoryCommandCenter';
export * from './command-center/MemoryCommandCenterAdvancedPanels';
export * from './command-center/MemoryCommandCenterChrome';
export * from './command-center/MemoryCommandCenterDoctorPanel';
export * from './command-center/MemoryCommandCenterPanels';

// dialogs
export * from './dialogs/ConnectWizardDialog';
export * from './dialogs/MemoryArchiveRestoreDialog';
export { default as MemoryClearAllDialog } from './dialogs/MemoryClearAllDialog';
export { default as MemoryCreateDialog } from './dialogs/MemoryCreateDialog';
export { default as MemoryEditDialog } from './dialogs/MemoryEditDialog';
export * from './dialogs/MemoryImportReviewDialog';
export { default as ShareRulesDialog } from './dialogs/ShareRulesDialog';

// guides
export { default as MemoryGuide } from './guides/MemoryGuide';
export * from './guides/MemoryLayerGuide';

// hooks
export * from './hooks/useMemoryArchiveRestoreActions';
export * from './hooks/useMemoryDemoSeed';

// insights
export { default as MemoryContextPanel } from './insights/MemoryContextPanel';
export { default as MemoryHealthDashboard } from './insights/MemoryHealthDashboard';
export { default as MemoryKnowledgeGraph } from './insights/MemoryKnowledgeGraph';

// pending
export { default as PendingMemoryBadge } from './pending/PendingMemoryBadge';
export { default as PendingMemoryDialog } from './pending/PendingMemoryDialog';
export { default as PendingMemoryList } from './pending/PendingMemoryList';

// replay
export { default as ConversationRecallPanel } from './replay/ConversationRecallPanel';
export { default as ReplayMessageBubble } from './replay/ReplayMessageBubble';
export { default as SessionReplayPlayer } from './replay/SessionReplayPlayer';
export * from './replay/memoryLiveStream';
export * from './replay/replayTimeline';

// settings
export { default as MemorySettingsToggles } from './settings/MemorySettingsToggles';
export { default as MemoryTabSwitcher } from './settings/MemoryTabSwitcher';
export { default as MemoryTrashPanel } from './settings/MemoryTrashPanel';

// shared-context
export { default as SharedContextPanel } from './shared-context/SharedContextPanel';
export * from './shared-context/SharedContextMemoryHealthBanner';
export * from './shared-context/SharedContextTargetBinding';
export * from './shared-context/useSharedContextPanel';
