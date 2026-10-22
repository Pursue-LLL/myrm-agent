import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  ReviewLoopDashboard,
  LoopRoundData,
} from '../ReviewLoopDashboard';

describe('ReviewLoopDashboard', () => {
  const sampleRound1: LoopRoundData = {
    round_number: 1,
    perspective_reports: {
      correctness: {
        perspective: 'correctness',
        reviewer_name: 'correctness-reviewer',
        approved: false,
        findings: [
          {
            perspective: 'correctness',
            severity: 'critical',
            file_path: 'app/worker.py',
            issue: 'Unimplemented stub pass statement',
            suggestion: 'Implement concrete return value',
            line_number: 12,
          },
        ],
        summary: '1 critical issue found',
      },
      test_coverage: {
        perspective: 'test_coverage',
        reviewer_name: 'test_coverage-reviewer',
        approved: false,
        findings: [
          {
            perspective: 'test_coverage',
            severity: 'major',
            file_path: 'tests/test_worker.py',
            issue: 'Missing test coverage for new method',
            suggestion: 'Add unit tests asserting output',
            line_number: 1,
          },
        ],
        summary: '1 major test gap found',
      },
      simplicity: {
        perspective: 'simplicity',
        reviewer_name: 'simplicity-reviewer',
        approved: true,
        findings: [],
        summary: 'Clean and minimal',
      },
    },
    all_findings: [
      {
        perspective: 'correctness',
        severity: 'critical',
        file_path: 'app/worker.py',
        issue: 'Unimplemented stub pass statement',
        suggestion: 'Implement concrete return value',
        line_number: 12,
      },
      {
        perspective: 'test_coverage',
        severity: 'major',
        file_path: 'tests/test_worker.py',
        issue: 'Missing test coverage for new method',
        suggestion: 'Add unit tests asserting output',
        line_number: 1,
      },
    ],
    has_blocking_issues: true,
    fix_description: null,
    converged: false,
  };

  const sampleRound2Clean: LoopRoundData = {
    round_number: 2,
    perspective_reports: {
      correctness: {
        perspective: 'correctness',
        reviewer_name: 'correctness-reviewer',
        approved: true,
        findings: [],
        summary: 'Correctness passed cleanly',
      },
      test_coverage: {
        perspective: 'test_coverage',
        reviewer_name: 'test_coverage-reviewer',
        approved: true,
        findings: [],
        summary: 'Unit tests passed',
      },
      simplicity: {
        perspective: 'simplicity',
        reviewer_name: 'simplicity-reviewer',
        approved: true,
        findings: [],
        summary: 'Clean architecture',
      },
    },
    all_findings: [],
    has_blocking_issues: false,
    fix_description: 'Replaced stub pass with implementation and added unit test',
    converged: true,
  };

  it('renders round 1 with tri-perspective cards and findings', () => {
    render(
      <ReviewLoopDashboard
        loopId="loop-123"
        sessionId="chat-456"
        status="in_review"
        currentRound={1}
        maxRounds={3}
        isClean={false}
        rounds={[sampleRound1]}
      />,
    );

    expect(screen.getByTestId('review-loop-dashboard')).toBeInTheDocument();
    expect(screen.getByText('Round 1/3')).toBeInTheDocument();
    expect(screen.getByText('自愈复审中')).toBeInTheDocument();

    // Verify tri-perspective cards
    expect(screen.getByTestId('perspective-card-correctness')).toBeInTheDocument();
    expect(screen.getByTestId('perspective-card-test_coverage')).toBeInTheDocument();
    expect(screen.getByTestId('perspective-card-simplicity')).toBeInTheDocument();

    // Findings
    expect(screen.getByText('Unimplemented stub pass statement')).toBeInTheDocument();
    expect(screen.getByText('Missing test coverage for new method')).toBeInTheDocument();
  });

  it('renders converged clean diff state with approval button', () => {
    render(
      <ReviewLoopDashboard
        loopId="loop-123"
        sessionId="chat-456"
        status="converged"
        currentRound={2}
        maxRounds={3}
        isClean={true}
        rounds={[sampleRound1, sampleRound2Clean]}
        onApprove={vi.fn()}
      />,
    );

    expect(screen.getByTestId('clean-diff-badge')).toBeInTheDocument();
    expect(screen.getByText('Clean Diff 已收敛')).toBeInTheDocument();
    expect(screen.getByTestId('approve-clean-diff-button')).toBeInTheDocument();
    expect(screen.getByText('采纳交付 Clean Diff')).toBeInTheDocument();
  });

  it('calls onAdvanceRound when clicking advance round button', () => {
    const handleAdvance = vi.fn();
    render(
      <ReviewLoopDashboard
        loopId="loop-123"
        sessionId="chat-456"
        status="in_review"
        currentRound={1}
        maxRounds={3}
        isClean={false}
        rounds={[sampleRound1]}
        onAdvanceRound={handleAdvance}
      />,
    );

    const advanceBtn = screen.getByTestId('advance-round-button');
    expect(advanceBtn).toHaveTextContent('推进下一轮自愈修复 (Round 2)');
    fireEvent.click(advanceBtn);

    expect(handleAdvance).toHaveBeenCalledTimes(1);
    expect(handleAdvance).toHaveBeenCalledWith('loop-123');
  });

  it('calls onApprove when clicking approve button on clean diff', () => {
    const handleApprove = vi.fn();
    render(
      <ReviewLoopDashboard
        loopId="loop-789"
        sessionId="chat-456"
        status="converged"
        currentRound={2}
        maxRounds={3}
        isClean={true}
        rounds={[sampleRound1, sampleRound2Clean]}
        onApprove={handleApprove}
      />,
    );

    const approveBtn = screen.getByTestId('approve-clean-diff-button');
    fireEvent.click(approveBtn);

    expect(handleApprove).toHaveBeenCalledTimes(1);
    expect(handleApprove).toHaveBeenCalledWith('loop-789');
  });

  it('calls onClose when clicking close button', () => {
    const handleClose = vi.fn();
    render(
      <ReviewLoopDashboard
        loopId="loop-123"
        sessionId="chat-456"
        status="in_review"
        currentRound={1}
        maxRounds={3}
        isClean={false}
        rounds={[sampleRound1]}
        onClose={handleClose}
      />,
    );

    const closeBtn = screen.getByTestId('close-dashboard-button');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('filters findings when clicking on a perspective card', () => {
    render(
      <ReviewLoopDashboard
        loopId="loop-123"
        sessionId="chat-456"
        status="in_review"
        currentRound={1}
        maxRounds={3}
        isClean={false}
        rounds={[sampleRound1]}
      />,
    );

    // Initially both findings are visible
    expect(screen.getByText('Unimplemented stub pass statement')).toBeInTheDocument();
    expect(screen.getByText('Missing test coverage for new method')).toBeInTheDocument();

    // Click correctness perspective card to filter
    const correctnessCard = screen.getByTestId('perspective-card-correctness');
    fireEvent.click(correctnessCard);

    // Only correctness issue is visible
    expect(screen.getByText('Unimplemented stub pass statement')).toBeInTheDocument();
    expect(screen.queryByText('Missing test coverage for new method')).not.toBeInTheDocument();
  });
});
