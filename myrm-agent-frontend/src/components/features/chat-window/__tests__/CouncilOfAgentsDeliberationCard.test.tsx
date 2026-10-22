import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { CouncilOfAgentsDeliberationCard } from '../CouncilOfAgentsDeliberationCard';

describe('CouncilOfAgentsDeliberationCard', () => {
  it('renders header, topic, 5 phases, and 3 model proposal cards', () => {
    const handleDismiss = vi.fn();
    render(
      <CouncilOfAgentsDeliberationCard
        sessionId="sess-test-council"
        onDismiss={handleDismiss}
      />
    );

    expect(
      screen.getByRole('region', {
        name: /Council of Agents Multi-Model Deliberation Protocol/i,
      })
    ).toBeInTheDocument();
    expect(screen.getByText('Council of Agents Deliberation')).toBeInTheDocument();
    expect(screen.getByText('Session: sess-test-council')).toBeInTheDocument();

    // Verify 5 phases in nav
    expect(screen.getAllByText(/1\. Blind Proposal/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/2\. Cross Critique/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/3\. Rebuttal & Defense/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/4\. Consensus Synthesis/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/5\. Finalized/i).length).toBeGreaterThan(0);

    // Verify 3 base model cards
    expect(screen.getByRole('button', { name: /Claude-3.5-Sonnet/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /GPT-4o/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /DeepSeek-R1/i })).toBeInTheDocument();

    // Verify active proposal details
    expect(screen.getByText(/Reasoning Trajectory:/i)).toBeInTheDocument();
    expect(screen.getByText(/Sub-millisecond state access/i)).toBeInTheDocument();

    // Dismiss test
    const closeBtn = screen.getByLabelText('Close council deliberation card');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('switches active proposal view when clicking different model cards', () => {
    render(<CouncilOfAgentsDeliberationCard />);

    // Click GPT-4o card
    const gptBtn = screen.getByRole('button', { name: /GPT-4o/i });
    fireEvent.click(gptBtn);

    expect(
      screen.getAllByText(/Stateless Event-Driven Gateway with Redis Cache-Aside/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/Cost-effective elastic scaling/i)).toBeInTheDocument();
  });

  it('submits defense rebuttal for an unrefuted critique', () => {
    render(<CouncilOfAgentsDeliberationCard />);

    // Click + Add Defense Rebuttal
    const addRebuttalBtn = screen.getByRole('button', { name: /\+ Add Defense Rebuttal/i });
    fireEvent.click(addRebuttalBtn);

    const textarea = screen.getByPlaceholderText(/Provide counter-evidence or mitigation/i);
    fireEvent.change(textarea, { target: { value: 'Redis mutex locks prevent cache stampede.' } });

    const submitBtn = screen.getByRole('button', { name: /Submit Rebuttal/i });
    fireEvent.click(submitBtn);

    expect(screen.getByText(/Redis mutex locks prevent cache stampede/i)).toBeInTheDocument();
  });

  it('advances through phases and displays synthesized consensus verdict', () => {
    const handlePhaseAdvanced = vi.fn();
    const handleConsensusReached = vi.fn();
    render(
      <CouncilOfAgentsDeliberationCard
        onPhaseAdvanced={handlePhaseAdvanced}
        onConsensusReached={handleConsensusReached}
      />
    );

    // Initial phase is blind_proposal
    expect(screen.getByText('Current:')).toBeInTheDocument();

    // Advance to cross_critique
    const advanceBtn = screen.getByRole('button', { name: /Advance to Next Phase →/i });
    fireEvent.click(advanceBtn);
    expect(handlePhaseAdvanced).toHaveBeenCalledWith('cross_critique');

    // Advance to rebuttal
    fireEvent.click(advanceBtn);
    expect(handlePhaseAdvanced).toHaveBeenCalledWith('rebuttal');

    // Advance to consensus synthesis
    const synthBtn = screen.getByRole('button', { name: /Synthesize Consensus/i });
    fireEvent.click(synthBtn);
    expect(handlePhaseAdvanced).toHaveBeenCalledWith('consensus_synthesis');
    expect(handleConsensusReached).toHaveBeenCalledTimes(1);

    // Consensus verdict should be displayed
    expect(screen.getByText(/Consensus Verdict Reached/i)).toBeInTheDocument();
    expect(screen.getByText(/Confidence Rating: 92%/i)).toBeInTheDocument();
    expect(screen.getByText(/Key Architectural Tradeoffs:/i)).toBeInTheDocument();
    expect(screen.getByText(/Dissenting Opinions:/i)).toBeInTheDocument();
  });
});
