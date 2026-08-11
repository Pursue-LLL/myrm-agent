import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const storeMock = vi.hoisted(() => ({
  securityPreset: 'hitl' as SecurityPreset,
  setSecurityPreset: vi.fn(),
  actionMode: 'agent' as ActionMode,
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof storeMock) => unknown) => selector(storeMock),
}));

const resolveMock = vi.hoisted(() => vi.fn());

vi.mock('@/store/chat/securityPreset', () => ({
  resolvePresetWithYoloMutexEnsured: resolveMock,
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: () => null,
}));

vi.mock('@/components/primitives/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onClick,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
  }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
}));

import SecurityPresetSelector from '../SecurityPresetSelector';
import type { ActionMode } from '@/store/chat/types/sessionConfig';
import type { SecurityPreset } from '@/store/chat/types/chatState';
import { act } from 'react';

const clickOption = async () => {
  await act(async () => {
    fireEvent.click(screen.getAllByRole('button')[1]);
  });
};

describe('SecurityPresetSelector', () => {
  beforeEach(() => {
    storeMock.securityPreset = 'hitl';
    storeMock.actionMode = 'agent';
    storeMock.setSecurityPreset.mockReset();
    resolveMock.mockReset();
    resolveMock.mockResolvedValue(null);
  });

  it('renders nothing outside agent mode', () => {
    storeMock.actionMode = 'fast';
    const { container } = render(<SecurityPresetSelector />);
    expect(container).toBeEmptyDOMElement();
  });

  it('skips setPreset when the mutex resolves to null (YOLO-only disarm)', async () => {
    resolveMock.mockResolvedValue(null);
    render(<SecurityPresetSelector />);
    await clickOption();
    expect(storeMock.setSecurityPreset).not.toHaveBeenCalled();
  });

  it('applies the resolved preset when the mutex returns a new value', async () => {
    resolveMock.mockResolvedValue('accept_edits' as SecurityPreset);
    render(<SecurityPresetSelector />);
    await clickOption();
    expect(storeMock.setSecurityPreset).toHaveBeenCalledWith('accept_edits');
  });

  it('passes the current and selected preset into the mutex', async () => {
    storeMock.securityPreset = 'explore';
    resolveMock.mockResolvedValue(null);
    render(<SecurityPresetSelector />);
    await clickOption();
    expect(resolveMock).toHaveBeenCalledWith('explore', 'hitl');
  });
});
