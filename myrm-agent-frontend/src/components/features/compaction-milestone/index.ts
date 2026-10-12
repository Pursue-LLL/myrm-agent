/**
 * [INPUT]
 * - CompactedMilestoneCard, BranchSummaryCard, ReadOnlyTimeMachineDrawer from ./
 * - Types from ./compactionTypes
 *
 * [OUTPUT]
 * - Public barrel exports for compaction-milestone feature package
 *
 * [POS]
 * CompactedMilestoneCardAndBranchSummaryVisualizer module entrypoint (Item 27).
 */

export { CompactedMilestoneCard } from './CompactedMilestoneCard';
export { BranchSummaryCard } from './BranchSummaryCard';
export { ReadOnlyTimeMachineDrawer } from './ReadOnlyTimeMachineDrawer';
export type {
  CompactionEntry,
  BranchSummaryEntry,
  CompactedMessageSnapshot,
} from './compactionTypes';
