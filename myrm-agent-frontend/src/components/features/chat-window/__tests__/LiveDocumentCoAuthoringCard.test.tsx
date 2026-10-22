import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LiveDocumentCoAuthoringCard } from '../LiveDocumentCoAuthoringCard';

describe('LiveDocumentCoAuthoringCard', () => {
  it('renders section, header, document ID, and default document blocks', () => {
    render(<LiveDocumentCoAuthoringCard chatId="chat-spec-101" documentId="doc-test-72" />);

    expect(
      screen.getByRole('region', {
        name: /Live Document Co-Authoring Ledger/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/chat-spec-101/i)).toBeInTheDocument();
    expect(screen.getByText(/doc-test-72/i)).toBeInTheDocument();

    // Default blocks
    expect(screen.getByText('block-01-title')).toBeInTheDocument();
    expect(screen.getAllByText('block-02-exec-summary').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('block-03-security-sla')).toBeInTheDocument();
  });

  it('switches to Roster tab and displays human and agent collaborators', () => {
    render(<LiveDocumentCoAuthoringCard chatId="chat-spec-101" />);

    const rosterTab = screen.getByRole('button', { name: /Roster/i });
    fireEvent.click(rosterTab);

    expect(screen.getByText('Alice (Lead Architect)')).toBeInTheDocument();
    expect(screen.getByText('Alice Copilot')).toBeInTheDocument();
    expect(screen.getByText('Bob (Security Auditor)')).toBeInTheDocument();
    expect(screen.getByText('Bob Copilot')).toBeInTheDocument();

    // Verify Principal human link
    expect(screen.getByText(/Principal Owner: user-alice/i)).toBeInTheDocument();
    expect(screen.getByText(/Principal Owner: user-bob/i)).toBeInTheDocument();
  });

  it('handles lease acquisition and release on a block', async () => {
    const handleAcquire = vi.fn().mockResolvedValue(true);
    const handleRelease = vi.fn().mockResolvedValue(true);

    render(
      <LiveDocumentCoAuthoringCard
        chatId="chat-spec-101"
        onAcquireLease={handleAcquire}
        onReleaseLease={handleRelease}
      />,
    );

    const acquireBtn = screen.getByRole('button', { name: /Acquire Lease/i });
    fireEvent.click(acquireBtn);

    expect(handleAcquire).toHaveBeenCalledWith('block-02-exec-summary', 'user-alice');
    expect(await screen.findByText(/Lease acquired on block-02-exec-summary/i)).toBeInTheDocument();

    const releaseBtn = screen.getByRole('button', { name: /Release/i });
    fireEvent.click(releaseBtn);

    expect(handleRelease).toHaveBeenCalledWith('block-02-exec-summary', 'user-alice');
    expect(await screen.findByText(/Lease released for block block-02-exec-summary/i)).toBeInTheDocument();
  });

  it('commits a delta edit with intent reason and displays in Intent Ledger', async () => {
    const handleCommit = vi.fn().mockResolvedValue(true);

    render(
      <LiveDocumentCoAuthoringCard
        chatId="chat-spec-101"
        onCommitDelta={handleCommit}
      />,
    );

    const editArea = screen.getByLabelText(/Edit Block Content:/i);
    const intentInput = screen.getByLabelText(/Intent Reason \(Audit Trace\):/i);

    fireEvent.change(editArea, { target: { value: 'Updated executive summary content.' } });
    fireEvent.change(intentInput, { target: { value: 'Clarified architecture requirements' } });

    const commitBtn = screen.getByRole('button', { name: /Commit Delta with Intent/i });
    fireEvent.click(commitBtn);

    expect(handleCommit).toHaveBeenCalled();
    expect(await screen.findByText(/updated to v3 by Alice \(Lead Architect\)/i)).toBeInTheDocument();

    // Check Intent Ledger tab
    const ledgerTab = screen.getByRole('button', { name: /Intent Ledger/i });
    fireEvent.click(ledgerTab);

    expect(screen.getByText(/Clarified architecture requirements/i)).toBeInTheDocument();
  });

  it('switches to Staging Proposals tab, accepts a proposal, and triggers conflict arbitration', async () => {
    const handleAccept = vi.fn().mockResolvedValue(true);
    const handleArbitrate = vi.fn().mockResolvedValue({
      resolved: true,
      winningContent: 'Hardened SLA content',
      strategy: 'human_priority',
      summary: 'Arbitration passed via Human Priority rule.',
      stagingProposals: [],
      timestamp: Date.now(),
    });

    render(
      <LiveDocumentCoAuthoringCard
        chatId="chat-spec-101"
        onAcceptProposal={handleAccept}
        onArbitrate={handleArbitrate}
      />,
    );

    const proposalsTab = screen.getByRole('button', { name: /Staging Proposals/i });
    fireEvent.click(proposalsTab);

    expect(screen.getByText('prop-sec-opt-01')).toBeInTheDocument();

    // Accept proposal
    const acceptBtn = screen.getByRole('button', { name: /Accept & Merge/i });
    fireEvent.click(acceptBtn);

    expect(handleAccept).toHaveBeenCalledWith('prop-sec-opt-01');
    expect(await screen.findByText(/accepted and merged into live document/i)).toBeInTheDocument();

    // Arbitrate
    const arbitrateBtn = screen.getByRole('button', { name: /Simulate Conflict Arbitration/i });
    fireEvent.click(arbitrateBtn);

    expect(handleArbitrate).toHaveBeenCalled();
    expect(await screen.findByText(/Arbitration passed via Human Priority rule./i)).toBeInTheDocument();
  });
});
