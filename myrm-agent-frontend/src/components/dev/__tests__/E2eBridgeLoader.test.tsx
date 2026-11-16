import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/components/dev/E2EChatBridge', () => ({ default: () => <i data-testid="chat-bridge" /> }));
vi.mock('@/components/dev/E2EWikiBridge', () => ({ default: () => <i data-testid="wiki-bridge" /> }));

import E2eBridgeLoader from '@/components/dev/E2eBridgeLoader';

const originalLocation = window.location;

function setHostname(hostname: string): void {
  Object.defineProperty(window, 'location', { configurable: true, value: { hostname } });
}

afterEach(() => {
  vi.unstubAllEnvs();
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
});

describe('E2eBridgeLoader', () => {
  it.each(['127.0.0.1', 'localhost'])('mounts the chat and wiki bridges on %s in a non-production build', (host) => {
    setHostname(host);
    render(<E2eBridgeLoader />);

    expect(screen.getByTestId('chat-bridge')).toBeInTheDocument();
    expect(screen.getByTestId('wiki-bridge')).toBeInTheDocument();
  });

  it('mounts nothing in a production build, even on a loopback host', () => {
    vi.stubEnv('NODE_ENV', 'production');
    setHostname('127.0.0.1');
    const { container } = render(<E2eBridgeLoader />);

    expect(container).toBeEmptyDOMElement();
  });

  it('mounts nothing on a host that is not a local dev host', () => {
    setHostname('example.com');
    const { container } = render(<E2eBridgeLoader />);

    expect(container).toBeEmptyDOMElement();
  });
});
