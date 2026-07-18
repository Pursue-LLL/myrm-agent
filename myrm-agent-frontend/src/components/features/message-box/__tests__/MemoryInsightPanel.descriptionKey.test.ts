import { describe, expect, it } from 'vitest';
import type { MemoryBriefStatus } from '@/store/chat/types';
import { resolveBriefUnavailableDescriptionKey } from '../MemoryInsightPanel';

function skippedStatus(
  injection?: MemoryBriefStatus['injection']
): MemoryBriefStatus {
  return injection
    ? { state: 'skipped', injection }
    : { state: 'skipped' };
}

describe('resolveBriefUnavailableDescriptionKey', () => {
  it('returns injected key when injection applied', () => {
    expect(
      resolveBriefUnavailableDescriptionKey(
        skippedStatus({ state: 'applied', source: 'snapshot' })
      )
    ).toBe('briefUnavailableDescriptionInjected');
  });

  it('returns not injected key for missing context reasons', () => {
    expect(
      resolveBriefUnavailableDescriptionKey(
        skippedStatus({ state: 'not_applied', reason: 'missing_context' })
      )
    ).toBe('briefUnavailableDescriptionNotInjected');
    expect(
      resolveBriefUnavailableDescriptionKey(
        skippedStatus({ state: 'not_applied', reason: 'not_injected' })
      )
    ).toBe('briefUnavailableDescriptionNotInjected');
  });

  it('returns tools mode key for tools recall path', () => {
    expect(
      resolveBriefUnavailableDescriptionKey(
        skippedStatus({ state: 'not_applied', reason: 'recall_mode_tools' })
      )
    ).toBe('briefUnavailableDescriptionToolsMode');
  });

  it('returns already present key when context exists in turn', () => {
    expect(
      resolveBriefUnavailableDescriptionKey(
        skippedStatus({ state: 'not_applied', reason: 'already_present' })
      )
    ).toBe('briefUnavailableDescriptionAlreadyPresent');
  });

  it('returns system issue key for runtime failures', () => {
    expect(
      resolveBriefUnavailableDescriptionKey(
        skippedStatus({ state: 'not_applied', reason: 'load_error' })
      )
    ).toBe('briefUnavailableDescriptionSystemIssue');
  });

  it('falls back to generic description for missing status', () => {
    expect(resolveBriefUnavailableDescriptionKey(undefined)).toBe(
      'briefUnavailableDescription'
    );
  });
});

