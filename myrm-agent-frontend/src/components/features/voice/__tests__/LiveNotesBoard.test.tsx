/**
 * Unit tests for LiveNotesBoard — the in-meeting rolling notes surface.
 *
 * Covers every render branch the Live board can hit from a real snapshot: empty,
 * summary-only, decisions, risks, action items (with/without owner and due date),
 * and the line counter.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import type { LiveMeetingSnapshot } from '@/services/liveMeeting';

const t = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => t,
}));

vi.mock('lucide-react', () => ({
  ClipboardList: () => <span data-testid="icon-clipboard" />,
  ListChecks: () => <span data-testid="icon-checks" />,
  MessageSquareQuote: () => <span data-testid="icon-quote" />,
  TriangleAlert: () => <span data-testid="icon-alert" />,
}));

import LiveNotesBoard from '../LiveNotesBoard';

function snapshot(overrides: Partial<LiveMeetingSnapshot> = {}): LiveMeetingSnapshot {
  return {
    success: true,
    session_id: 'live-1',
    line_count: 0,
    transcript_chars: 0,
    refreshed: false,
    title: '',
    summary: '',
    decisions: [],
    debate_points: [],
    risks: [],
    action_items: [],
    published_wiki_paths: [],
    error: '',
    ...overrides,
  };
}

describe('LiveNotesBoard', () => {
  it('shows the empty state when there is no snapshot yet', () => {
    render(<LiveNotesBoard snapshot={null} />);
    expect(screen.getByTestId('live-notes-board')).toBeInTheDocument();
    expect(screen.getByText('empty')).toBeInTheDocument();
  });

  it('shows the empty state when the snapshot carries no usable content', () => {
    render(<LiveNotesBoard snapshot={snapshot()} />);
    expect(screen.getByText('empty')).toBeInTheDocument();
    // A zero line count must not render a misleading counter.
    expect(screen.queryByText('lines')).not.toBeInTheDocument();
  });

  it('renders the live line counter once lines exist', () => {
    render(<LiveNotesBoard snapshot={snapshot({ line_count: 12, summary: 'rolling' })} />);
    expect(screen.getByText('lines')).toBeInTheDocument();
  });

  it('renders the rolling summary', () => {
    render(<LiveNotesBoard snapshot={snapshot({ summary: 'Beta ships Friday.' })} />);
    expect(screen.getByText('summary')).toBeInTheDocument();
    expect(screen.getByText('Beta ships Friday.')).toBeInTheDocument();
    expect(screen.queryByText('empty')).not.toBeInTheDocument();
  });

  it('renders decisions as a list', () => {
    render(<LiveNotesBoard snapshot={snapshot({ summary: 's', decisions: ['Ship Friday', 'Cut scope'] })} />);
    expect(screen.getByText('decisions')).toBeInTheDocument();
    expect(screen.getByText('Ship Friday')).toBeInTheDocument();
    expect(screen.getByText('Cut scope')).toBeInTheDocument();
  });

  it('renders risks', () => {
    render(<LiveNotesBoard snapshot={snapshot({ summary: 's', risks: ['Vendor unsigned'] })} />);
    expect(screen.getByText('risks')).toBeInTheDocument();
    expect(screen.getByText('Vendor unsigned')).toBeInTheDocument();
  });

  it('renders action items with owner and due date', () => {
    render(
      <LiveNotesBoard
        snapshot={snapshot({
          summary: 's',
          action_items: [{ description: 'Sign the contract', owner: 'Bob', due_hint: 'Friday' }],
        })}
      />,
    );
    expect(screen.getByText('actionItems')).toBeInTheDocument();
    expect(screen.getByText('Sign the contract')).toBeInTheDocument();
    expect(screen.getByText(/Bob/)).toBeInTheDocument();
    expect(screen.getByText(/Friday/)).toBeInTheDocument();
  });

  it('falls back to unassigned and omits an absent due date', () => {
    render(
      <LiveNotesBoard
        snapshot={snapshot({
          summary: 's',
          action_items: [{ description: 'Draft checklist', owner: null, due_hint: null }],
        })}
      />,
    );
    expect(screen.getByText(/unassigned/)).toBeInTheDocument();
    expect(screen.queryByText(/due/)).not.toBeInTheDocument();
  });

  it('renders every populated section of a full snapshot at once', () => {
    render(
      <LiveNotesBoard
        snapshot={snapshot({
          line_count: 42,
          summary: 'Full meeting.',
          decisions: ['d1'],
          risks: ['r1'],
          action_items: [{ description: 'a1', owner: 'Carol', due_hint: 'Thursday' }],
        })}
      />,
    );
    for (const label of ['summary', 'decisions', 'risks', 'actionItems']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('Full meeting.')).toBeInTheDocument();
    expect(screen.getByText('d1')).toBeInTheDocument();
    expect(screen.getByText('r1')).toBeInTheDocument();
    expect(screen.getByText('a1')).toBeInTheDocument();
  });

  it('forwards the className to the board container', () => {
    render(<LiveNotesBoard snapshot={snapshot({ summary: 's' })} className="max-h-full" />);
    expect(screen.getByTestId('live-notes-board').className).toContain('max-h-full');
  });
});
