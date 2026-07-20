'use client';

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

vi.mock('../agent-config-panel/MediaCredentialInline', () => ({
  MediaCredentialInline: () => null,
}));

vi.mock('../agent-config-panel/CuPermissionInline', () => ({
  CuPermissionInline: () => null,
}));

const sandboxDeployMock = vi.hoisted(() => ({
  isSandbox: vi.fn(() => false),
  isLocalMode: vi.fn(() => true),
}));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isSandbox: sandboxDeployMock.isSandbox,
    isLocalMode: sandboxDeployMock.isLocalMode,
  };
});

const tPanel = (key: string) => {
  const map: Record<string, string> = {
    'builtinToolNames.external_cli': 'External CLI',
    'builtinToolDescs.external_cli': 'Delegate to external CLI agents',
    externalCliLocalOnlyHint:
      'External CLI delegation requires local or desktop mode. Cloud/sandbox hosts cannot spawn local CLI processes.',
    externalCliSetupHint: 'Two steps: register CLI backends and keep this switch on.',
    externalCliNoBackendHint: 'No enabled CLI backend found in Settings yet',
    externalCliOpenSettings: 'Configure External Agents in Settings',
  };
  return map[key] ?? key;
};

const baseProps = {
  localBuiltinTools: [] as string[],
  setLocalBuiltinTools: vi.fn(),
  localAutoRestoreDomains: [] as string[],
  setLocalAutoRestoreDomains: vi.fn(),
  setLocalBrowserSource: vi.fn(),
  setLocalDialogPolicy: vi.fn(),
  setLocalSessionRecording: vi.fn(),
  t: (key: string) => key,
  tAgent: (key: string) => key,
  tPanel,
};

describe('BuiltinToolsPanel external_cli sandbox gate', () => {
  it('allows toggling external_cli in local mode', async () => {
    sandboxDeployMock.isSandbox.mockReturnValue(false);
    sandboxDeployMock.isLocalMode.mockReturnValue(true);
    const setTools = vi.fn();

    render(
      <BuiltinToolsPanel
        {...baseProps}
        localBuiltinTools={[]}
        setLocalBuiltinTools={setTools}
      />,
    );

    const card = screen.getByTestId('builtin-external_cli');
    expect(card.className).not.toMatch(/cursor-not-allowed/);
    await userEvent.click(card);
    expect(setTools).toHaveBeenCalled();
    expect(screen.queryByText(/Cloud\/sandbox hosts cannot spawn/i)).not.toBeInTheDocument();
  });

  it('blocks enabling external_cli in sandbox mode and shows local-only hint', async () => {
    sandboxDeployMock.isSandbox.mockReturnValue(true);
    sandboxDeployMock.isLocalMode.mockReturnValue(false);
    const setTools = vi.fn();

    render(
      <BuiltinToolsPanel
        {...baseProps}
        localBuiltinTools={[]}
        setLocalBuiltinTools={setTools}
      />,
    );

    const card = screen.getByTestId('builtin-external_cli');
    expect(card.className).toMatch(/cursor-not-allowed/);
    expect(screen.getByText(/Cloud\/sandbox hosts cannot spawn/i)).toBeInTheDocument();
    await userEvent.click(card);
    expect(setTools).not.toHaveBeenCalled();
  });

  it('shows external CLI setup section when enabled in local mode', () => {
    sandboxDeployMock.isSandbox.mockReturnValue(false);
    sandboxDeployMock.isLocalMode.mockReturnValue(true);

    render(
      <BuiltinToolsPanel
        {...baseProps}
        localBuiltinTools={['external_cli']}
      />,
    );

    expect(screen.getByText(/Two steps: register CLI backends/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Configure External Agents/i })).toHaveAttribute(
      'href',
      '/settings/developer',
    );
  });
});
