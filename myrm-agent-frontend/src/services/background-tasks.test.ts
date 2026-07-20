import { describe, expect, it } from 'vitest';
import { evictedFilenameFromVaultRef } from '@/services/background-tasks';

describe('evictedFilenameFromVaultRef', () => {
  it('returns basename when ref is already a filename', () => {
    expect(evictedFilenameFromVaultRef('output_deadbeef.txt')).toBe('output_deadbeef.txt');
  });

  it('strips legacy relative paths from Core spill rows', () => {
    expect(evictedFilenameFromVaultRef('.context/chat-1/evicted/output_abcd1234.txt')).toBe(
      'output_abcd1234.txt',
    );
  });
});
