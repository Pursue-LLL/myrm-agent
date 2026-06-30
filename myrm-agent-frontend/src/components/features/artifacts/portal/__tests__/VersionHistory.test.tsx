import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import React from 'react';

vi.mock('next-intl', () => ({
  useTranslations: () => {
    const t = (key: string, params?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'versions.history': 'Version History',
        'versions.latest': 'Latest',
        'versions.currentVersion': 'Current Version',
        'versions.justNow': 'Just now',
        'versions.rollback': 'Rollback',
        'versions.backToLatest': 'Back to latest',
        'versions.rollbackConfirm.title': 'Rollback Confirm',
        'versions.rollbackConfirm.cancel': 'Cancel',
        'versions.rollbackConfirm.confirm': 'Confirm',
      };
      if (key === 'versions.minutesAgo') return `${params?.count}m ago`;
      if (key === 'versions.hoursAgo') return `${params?.count}h ago`;
      if (key === 'versions.daysAgo') return `${params?.count}d ago`;
      if (key === 'versions.totalVersions') return `${params?.count} versions`;
      if (key === 'versions.viewingHistoryBanner') return `Viewing v${params?.version}`;
      if (key === 'versions.rollbackConfirm.description')
        return `Rollback to v${params?.version}?`;
      return map[key] ?? key;
    };
    return t;
  },
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div data-testid="tooltip">{children}</div>,
}));

vi.mock('@/components/primitives/dropdown-menu', () => ({
  DropdownMenu: ({ children, open, onOpenChange }: { children: React.ReactNode; open: boolean; onOpenChange: (v: boolean) => void }) => (
    <div data-testid="dropdown-menu" data-open={String(open)} onClick={() => onOpenChange(!open)}>
      {children}
    </div>
  ),
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div data-testid="dropdown-content">{children}</div>,
  DropdownMenuItem: ({ children, onClick, className }: { children: React.ReactNode; onClick?: () => void; className?: string }) => (
    <div role="menuitem" onClick={onClick} className={className} data-testid="menu-item">
      {children}
    </div>
  ),
  DropdownMenuSeparator: () => <hr />,
}));

vi.mock('@/components/primitives/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button onClick={onClick}>{children}</button>
  ),
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
}));

import VersionHistory, { VersionHistoryBanner } from '../VersionHistory';
import type { ArtifactVersion } from '@/store/chat/types';

function makeVersion(overrides: Partial<ArtifactVersion> & { versionNumber: number }): ArtifactVersion {
  return {
    versionId: `v-${overrides.versionNumber}`,
    content: `content-${overrides.versionNumber}`,
    createdAt: new Date(Date.now() - 60000 * overrides.versionNumber).toISOString(),
    ...overrides,
  };
}

const versions: ArtifactVersion[] = [
  makeVersion({ versionNumber: 1, description: 'Initial draft' }),
  makeVersion({ versionNumber: 2, description: 'Added styling' }),
  makeVersion({ versionNumber: 3 }),
];

describe('VersionHistory', () => {
  let onSwitchVersion: ReturnType<typeof vi.fn>;
  let onRollback: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onSwitchVersion = vi.fn();
    onRollback = vi.fn();
  });

  it('renders nothing when versions is empty', () => {
    const { container } = render(
      <VersionHistory versions={[]} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    expect(container.querySelector('[data-testid="dropdown-menu"]')).toBeNull();
  });

  it('shows current version number (latest=v3) in trigger', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const btn = screen.getByLabelText('Version History');
    expect(btn.textContent).toContain('v3');
  });

  it('shows historical version number when viewingIndex >= 0', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={0} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const btn = screen.getByLabelText('Version History');
    expect(btn.textContent).toContain('v1');
  });

  it('disables trigger button when isGenerating', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={true} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const btn = screen.getByLabelText('Version History');
    expect(btn.hasAttribute('disabled')).toBe(true);
  });

  it('applies amber highlight when viewing history', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const btn = screen.getByLabelText('Version History');
    expect(btn.className).toContain('amber');
  });

  it('renders dropdown content with "Current Version" and all version items', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    expect(screen.getByText('Current Version')).toBeDefined();
    const items = screen.getAllByTestId('menu-item');
    expect(items.length).toBe(4);
  });

  it('shows descriptions for versions that have them', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    expect(screen.getByText('Initial draft')).toBeDefined();
    expect(screen.getByText('Added styling')).toBeDefined();
  });

  it('calls onSwitchVersion(-1) when clicking "Current Version"', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    fireEvent.click(screen.getByText('Current Version').closest('[data-testid="menu-item"]')!);
    expect(onSwitchVersion).toHaveBeenCalledWith(-1);
  });

  it('calls onSwitchVersion with correct index for a specific version', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const items = screen.getAllByTestId('menu-item');
    const v1Item = items.find((el) => el.textContent?.includes('v1'));
    expect(v1Item).toBeDefined();
    fireEvent.click(v1Item!);
    expect(onSwitchVersion).toHaveBeenCalledWith(0);
  });

  it('highlights currently selected version with bg-primary/10', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const currentItem = screen.getByText('Current Version').closest('[data-testid="menu-item"]');
    expect(currentItem?.className).toContain('bg-primary/10');
  });

  it('shows rollback buttons for non-latest, non-selected versions', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const rollbackBtns = screen.getAllByLabelText('Rollback');
    expect(rollbackBtns.length).toBe(2);
  });

  it('opens rollback confirmation and calls onRollback on confirm', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const rollbackBtns = screen.getAllByLabelText('Rollback');
    fireEvent.click(rollbackBtns[0]);
    expect(screen.getByText('Rollback Confirm')).toBeDefined();
    fireEvent.click(screen.getByText('Confirm'));
    expect(onRollback).toHaveBeenCalled();
  });

  it('does not call onRollback when cancel is clicked', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const rollbackBtns = screen.getAllByLabelText('Rollback');
    fireEvent.click(rollbackBtns[0]);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onRollback).not.toHaveBeenCalled();
  });

  it('shows relative time labels', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    expect(screen.getByText('1m ago')).toBeDefined();
    expect(screen.getByText('2m ago')).toBeDefined();
    expect(screen.getByText('3m ago')).toBeDefined();
  });

  it('shows "Latest" badge on the most recent version item', () => {
    render(
      <VersionHistory versions={versions} viewingIndex={-1} isGenerating={false} onSwitchVersion={onSwitchVersion} onRollback={onRollback} />,
    );
    const latestBadges = screen.getAllByText('Latest');
    expect(latestBadges.length).toBeGreaterThanOrEqual(2);
  });
});

describe('VersionHistoryBanner', () => {
  it('renders nothing when viewingIndex is -1 (viewing latest)', () => {
    const { container } = render(
      <VersionHistoryBanner versions={versions} viewingIndex={-1} onBackToLatest={vi.fn()} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('shows banner with correct version number', () => {
    render(
      <VersionHistoryBanner versions={versions} viewingIndex={1} onBackToLatest={vi.fn()} />,
    );
    expect(screen.getByText('Viewing v2')).toBeDefined();
  });

  it('calls onBackToLatest when clicking back button', () => {
    const onBack = vi.fn();
    render(<VersionHistoryBanner versions={versions} viewingIndex={0} onBackToLatest={onBack} />);
    fireEvent.click(screen.getByText('Back to latest'));
    expect(onBack).toHaveBeenCalledOnce();
  });

  it('renders nothing for out-of-range viewingIndex', () => {
    const { container } = render(
      <VersionHistoryBanner versions={versions} viewingIndex={99} onBackToLatest={vi.fn()} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('applies amber styling for historical warning banner', () => {
    render(
      <VersionHistoryBanner versions={versions} viewingIndex={0} onBackToLatest={vi.fn()} />,
    );
    const banner = screen.getByText('Viewing v1').closest('div');
    expect(banner?.className).toContain('amber');
  });
});
