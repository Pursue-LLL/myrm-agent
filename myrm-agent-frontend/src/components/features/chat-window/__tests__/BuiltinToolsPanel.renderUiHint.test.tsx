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
  useFeatureEntitlements: () => ({ canUseCron: true, canUseVnc: true, isLoading: false }),
}));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isSandbox: () => false,
    isLocalMode: () => true,
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
    renderUiWebOnlyHint:
      'Inline interactive UI renders only in Web Chat and the desktop app. Telegram, scheduled tasks, and other channels cannot display inline forms or charts.',
    'builtinToolNames.render_ui': 'Interactive UI',
    'builtinToolDescs.render_ui': 'Fill forms in chat',
  };
  return map[key] ?? key;
};

describe('BuiltinToolsPanel render_ui surface hint', () => {
  it('shows web-only hint when render_ui is enabled', () => {
    render(
      <BuiltinToolsPanel
        localBuiltinTools={['render_ui']}
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
      screen.getByText(/Inline interactive UI renders only in Web Chat/i),
    ).toBeInTheDocument();
  });

  it('hides web-only hint when render_ui is disabled', () => {
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
      screen.queryByText(/Inline interactive UI renders only in Web Chat/i),
    ).not.toBeInTheDocument();
  });
});
