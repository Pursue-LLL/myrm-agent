import { describe, expect, it } from 'vitest';
import type { ChannelIngressMode } from '@/lib/channels/connectivity';

describe('connectivity types', () => {
  it('accepts server ingress modes', () => {
    const outbound: ChannelIngressMode = 'outbound';
    const inbound: ChannelIngressMode = 'inbound';
    expect(outbound).toBe('outbound');
    expect(inbound).toBe('inbound');
  });
});
