'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BuiltinToolsPanel } from '../agent-config-panel/BuiltinToolsPanel';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock('@/hooks/useFeatureEntitlements', () => ({
  useFeatureEntitlements: () => ({ canUseCron: true, isLoading: false }),
}));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isSandbox: () => false,
  };
});

vi.mock('../agent-config-panel/MediaCredentialInline', () => ({
  MediaCredentialInline: () => null,
}));

vi.mock('../agent-config-panel/CuPermissionInline', () => ({
  CuPermissionInline: () => null,
}));

const tPanel = (key: string) => {
  const map: Record<string, string> = {
    browserDelegateHint:
      'For long or parallel web work, ask your agent to delegate browser tasks to the browser specialist while other sub-agents handle research or analysis.',
    'builtinToolNames.browser': 'Browser',
    'builtinToolDescs.browser': 'Automate web pages',
    autoRestoreDomains: 'Auto-restore domains',
    autoRestoreDomainsDesc: 'Domains to restore',
  };
  return map[key] ?? key;
};

describe('BuiltinToolsPanel browser delegate hint', () => {
  it('shows delegate hint when browser tool is enabled', () => {
    render(
      <BuiltinToolsPanel
        localBuiltinTools={['browser']}
        setLocalBuiltinTools={() => undefined}
        localAutoRestoreDomains={[]}
        setLocalAutoRestoreDomains={() => undefined}
        setLocalBrowserSource={() => undefined}
        setLocalDialogPolicy={() => undefined}
        setLocalSessionRecording={() => undefined}
        t={(key) => key}
        tAgent={(key) => key}
        tPanel={tPanel}
      />,
    );

    expect(
      screen.getByText(/delegate browser tasks to the browser specialist/i),
    ).toBeInTheDocument();
  });

  it('hides browser sub-config when browser tool is disabled', () => {
    render(
      <BuiltinToolsPanel
        localBuiltinTools={['web_search']}
        setLocalBuiltinTools={() => undefined}
        localAutoRestoreDomains={[]}
        setLocalAutoRestoreDomains={() => undefined}
        setLocalBrowserSource={() => undefined}
        setLocalDialogPolicy={() => undefined}
        setLocalSessionRecording={() => undefined}
        t={(key) => key}
        tAgent={(key) => key}
        tPanel={tPanel}
      />,
    );

    expect(
      screen.queryByText(/delegate browser tasks to the browser specialist/i),
    ).not.toBeInTheDocument();
  });
});
