import type { WikiDedupProgress } from '@/services/wikiService';

export const DEDUP_POLL_INTERVAL_MS = 500;
export const DEDUP_POLL_MAX_ATTEMPTS = 120;

export function isDedupScanTerminalPhase(phase: WikiDedupProgress['phase']): boolean {
  return phase === 'done' || phase === 'failed' || phase === 'idle';
}

export function shouldResumeDedupPoll(phase: WikiDedupProgress['phase']): boolean {
  return phase === 'scanning' || phase === 'grouping';
}

export function shouldNotifyDedupScanFailedOnMount(phase: WikiDedupProgress['phase']): boolean {
  return phase === 'failed';
}
