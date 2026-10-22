/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CompetitorMigrationCard } from '../command-center/CompetitorMigrationCard';
import type { CompetitorDetectResponseDTO, CompetitorIngestResponseDTO } from '@/services/memory/competitorMigration';

const { mockDetectCompetitors, mockIngestCompetitor } = vi.hoisted(() => ({
  mockDetectCompetitors: vi.fn(),
  mockIngestCompetitor: vi.fn(),
}));

const stableT = (key: string, params?: Record<string, unknown>) =>
  params && 'count' in params ? `${key}:${String(params.count)}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/memory/competitorMigration', () => ({
  detectCompetitors: mockDetectCompetitors,
  ingestCompetitor: mockIngestCompetitor,
}));

describe('CompetitorMigrationCard', () => {
  const detection: CompetitorDetectResponseDTO = {
    detected_competitors: ['hermes', 'claude_code'],
    hermes_dir: '/Users/test/.hermes',
    claude_code_rule_path: '/Users/test/projects/CLAUDE.md',
    codex_rule_path: null,
  };

  const ingestion: CompetitorIngestResponseDTO = {
    success: true,
    imported_rules_count: 2,
    imported_skills_count: 5,
    imported_memories_count: 8,
    details: ['Ingested 8 memory files from Hermes into memories/'],
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state and the pointer to whole-app backup before scanning', () => {
    render(<CompetitorMigrationCard />);

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('empty')).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', '/settings/workbench');
  });

  it('has no bundle export or restore surface any more', () => {
    render(<CompetitorMigrationCard />);

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });

  it('detects assistants and imports one with a one-click action', async () => {
    mockDetectCompetitors.mockResolvedValueOnce(detection);
    mockIngestCompetitor.mockResolvedValueOnce(ingestion);

    render(<CompetitorMigrationCard />);
    fireEvent.click(screen.getByRole('button', { name: 'scan' }));

    await waitFor(() => expect(mockDetectCompetitors).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Hermes Agent')).toBeInTheDocument();
    expect(screen.getByText('Claude Code')).toBeInTheDocument();
    expect(screen.getByText('foundCount:2')).toBeInTheDocument();

    const importButtons = screen.getAllByRole('button', { name: 'import' });
    expect(importButtons).toHaveLength(2);
    fireEvent.click(importButtons[0]);

    await waitFor(() =>
      expect(mockIngestCompetitor).toHaveBeenCalledWith({
        competitor: 'hermes',
        source_path: '/Users/test/.hermes',
      }),
    );

    expect(await screen.findByText('resultTitle')).toBeInTheDocument();
    expect(screen.getByText('memories:8')).toBeInTheDocument();
    expect(screen.getByText('skills:5')).toBeInTheDocument();
    expect(screen.getByText('rules:2')).toBeInTheDocument();
    // Server wording is never surfaced to the user.
    expect(screen.queryByText(/Ingested 8 memory files/)).not.toBeInTheDocument();
  });

  it('shows localized copy instead of the server message when scanning fails', async () => {
    mockDetectCompetitors.mockRejectedValueOnce(new Error('ECONNRESET internal stack'));

    render(<CompetitorMigrationCard />);
    fireEvent.click(screen.getByRole('button', { name: 'scan' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('errors.scan');
    expect(screen.queryByText(/ECONNRESET/)).not.toBeInTheDocument();
  });

  it('shows localized copy when an import fails', async () => {
    mockDetectCompetitors.mockResolvedValueOnce(detection);
    mockIngestCompetitor.mockRejectedValueOnce(new Error('boom'));

    render(<CompetitorMigrationCard />);
    fireEvent.click(screen.getByRole('button', { name: 'scan' }));
    const importButtons = await screen.findAllByRole('button', { name: 'import' });
    fireEvent.click(importButtons[0]);

    expect(await screen.findByRole('alert')).toHaveTextContent('errors.import');
  });
});
