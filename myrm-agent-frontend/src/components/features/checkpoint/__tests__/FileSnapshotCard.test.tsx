/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import FileSnapshotCard from '../FileSnapshotCard';
import { FileSnapshotInfo } from '@/services/checkpoint';

const translations: Record<string, string> = {
  'effects.database': 'database changes',
  'effects.container_cloud': 'container or cloud operations',
  'effects.network_mutation': 'network requests',
};

const tFn = (key: string, values?: Record<string, string | number>): string => {
  if (values?.effects !== undefined) return String(values.effects);
  return translations[key] ?? key;
};
tFn.has = (key: string): boolean => key in translations;

vi.mock('next-intl', () => ({
  useTranslations: () => tFn,
}));

const baseSnapshot = (overrides: Partial<FileSnapshotInfo> = {}): FileSnapshotInfo => ({
  snapshotId: 'snap-1',
  workingDir: '/ws',
  trigger: 'manual',
  createdAt: 1710000000,
  fileCount: 3,
  description: '',
  externalEffects: [],
  agentId: null,
  ...overrides,
});

const renderCard = (snapshot: FileSnapshotInfo) =>
  render(
    <FileSnapshotCard
      snapshot={snapshot}
      onRestore={() => {}}
      onViewDiff={() => {}}
      onDelete={() => {}}
      isLoading={false}
    />,
  );

describe('FileSnapshotCard', () => {
  it('renders mapped plain-language labels for known external effects', () => {
    renderCard(baseSnapshot({ externalEffects: ['database', 'container_cloud'] }));
    const badge = screen.getByTitle(
      'database changes, container or cloud operations',
    );
    expect(badge).toBeInTheDocument();
  });

  it('falls back to the raw category for unknown external effects', () => {
    renderCard(baseSnapshot({ externalEffects: ['custom_effect'] }));
    const badge = screen.getByTitle('custom_effect');
    expect(badge).toBeInTheDocument();
  });

  it('shows the restore warning with mapped labels when restoring', () => {
    renderCard(baseSnapshot({ externalEffects: ['network_mutation'] }));
    fireEvent.click(screen.getByText('restore'));
    expect(screen.getByText('network requests')).toBeInTheDocument();
  });

  it('does not render external effects UI when none exist', () => {
    renderCard(baseSnapshot({ externalEffects: [] }));
    expect(screen.queryByText('externalEffects')).not.toBeInTheDocument();
  });
});
