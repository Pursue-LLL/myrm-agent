/** @vitest-environment jsdom */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkingMemoryBoard } from '../WorkingMemoryBoard';

describe('WorkingMemoryBoard Component', () => {
  it('renders nothing when no data provided', () => {
    const { container } = render(<WorkingMemoryBoard />);
    expect(container.firstChild).toBeNull();
  });

  it('renders goal, subtasks progression, and progress ratio correctly', () => {
    render(
      <WorkingMemoryBoard
        goal="Migrate DB to SQLite WAL mode"
        subtasks={[
          { id: 'step-1', title: 'Inspect existing schema', status: 'completed' },
          { id: 'step-2', title: 'Apply migration SQL', status: 'in_progress', notes: 'running DDL' },
          { id: 'step-3', title: 'Verify integrity', status: 'pending' },
        ]}
      />
    );

    expect(screen.getByTestId('working-memory-board')).toBeInTheDocument();
    expect(screen.getByText('Migrate DB to SQLite WAL mode')).toBeInTheDocument();
    expect(screen.getByText('1/3 (33%)')).toBeInTheDocument();
    expect(screen.getByText('Inspect existing schema')).toBeInTheDocument();
    expect(screen.getByText('running DDL')).toBeInTheDocument();
  });

  it('toggles expansion when header is clicked', () => {
    render(
      <WorkingMemoryBoard
        goal="Build dashboard"
        subtasks={[{ id: 'step-1', title: 'Setup Vite', status: 'completed' }]}
        initiallyExpanded={true}
      />
    );

    expect(screen.getByText('任务执行清单')).toBeInTheDocument();

    const header = screen.getByTestId('working-board-header');
    fireEvent.click(header);
    expect(screen.queryByText('任务执行清单')).not.toBeInTheDocument();

    fireEvent.click(header);
    expect(screen.getByText('任务执行清单')).toBeInTheDocument();
  });

  it('renders error traps and consolidation digest badge', () => {
    render(
      <WorkingMemoryBoard
        goal="Secure API endpoints"
        traps={[
          {
            fingerprint: 'cors_wildcard_rejected',
            avoidance_rule: 'Explicitly specify origin instead of wildcard',
            tool_name: 'api_validator',
          },
        ]}
        digestBadge={{
          id: 'digest-101',
          completedStepsCount: 3,
          ruleCount: 1,
        }}
      />
    );

    expect(screen.getByText('运行时避坑防线')).toBeInTheDocument();
    expect(screen.getByText('Explicitly specify origin instead of wildcard')).toBeInTheDocument();
    expect(screen.getByText('api_validator')).toBeInTheDocument();
    expect(screen.getByTestId('digest-badge')).toBeInTheDocument();
    expect(screen.getByText('已终态固化')).toBeInTheDocument();
  });
});
