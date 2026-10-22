import React, { act } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CanvasViewer } from '../CanvasViewer';
import { useCanvasGatingStore } from '../useCanvasGatingStore';

const stableT = (key: string, params?: Record<string, unknown>) => {
    if (params?.count !== undefined) {
      return `${key}:${params.count}`;
    }
    return key;
  };

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('CanvasViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCanvasGatingStore.getState().reset();
  });

  it('renders sandboxed iframe with strict sandbox policy and no allow-same-origin', async () => {
    let container: HTMLElement;
    await act(async () => {
      const res = render(
        <CanvasViewer
          content="<div>Canvas Interactive Widget</div>"
          title="Interactive Dashboard"
        />
      );
      container = res.container;
      await Promise.resolve();
    });

    const iframe = container!.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('sandbox')).toBe('allow-scripts allow-forms');
    expect(iframe?.getAttribute('sandbox')).not.toContain('allow-same-origin');
    expect(screen.getByText('Interactive Dashboard')).toBeInTheDocument();
    expect(screen.getByText('sandboxedIsolatedBadge')).toBeInTheDocument();
  });

  it('displays egress authorization banner when a pending network request exists', async () => {
    // Register pending request in store
    act(() => {
      useCanvasGatingStore.getState().registerEgressRequest({
        url: 'https://api.weather.com/forecast',
        domain: 'api.weather.com',
        method: 'GET',
      });
    });

    await act(async () => {
      render(
        <CanvasViewer
          content="<div>Weather Canvas</div>"
          title="Weather Widget"
        />
      );
      await Promise.resolve();
    });

    expect(screen.getByText('pendingEgressBadge:1')).toBeInTheDocument();
    expect(screen.getByText('api.weather.com')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /blockEgress/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /allowOnce/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /alwaysAllowDomain/i })).toBeInTheDocument();
  });

  it('handles user denial of egress request', async () => {
    act(() => {
      useCanvasGatingStore.getState().registerEgressRequest({
        url: 'https://malicious.tracker.io/collect',
        domain: 'malicious.tracker.io',
        method: 'POST',
      });
    });

    await act(async () => {
      render(
        <CanvasViewer
          content="<div>Tracker Canvas</div>"
          title="Tracker Test"
        />
      );
      await Promise.resolve();
    });

    const blockBtn = screen.getByRole('button', { name: /blockEgress/i });
    await act(async () => {
      fireEvent.click(blockBtn);
      await Promise.resolve();
    });

    expect(useCanvasGatingStore.getState().pendingRequests).toHaveLength(0);
    expect(useCanvasGatingStore.getState().isDomainAllowed('malicious.tracker.io')).toBe(false);
  });

  it('handles user approval with domain whitelisting', async () => {
    act(() => {
      useCanvasGatingStore.getState().registerEgressRequest({
        url: 'https://api.github.com/repos',
        domain: 'api.github.com',
        method: 'GET',
      });
    });

    await act(async () => {
      render(
        <CanvasViewer
          content="<div>GitHub Canvas</div>"
          title="Repo Inspector"
        />
      );
      await Promise.resolve();
    });

    const alwaysAllowBtn = screen.getByRole('button', { name: /alwaysAllowDomain/i });
    await act(async () => {
      fireEvent.click(alwaysAllowBtn);
      await Promise.resolve();
    });

    expect(useCanvasGatingStore.getState().pendingRequests).toHaveLength(0);
    expect(useCanvasGatingStore.getState().isDomainAllowed('api.github.com')).toBe(true);
  });
});
