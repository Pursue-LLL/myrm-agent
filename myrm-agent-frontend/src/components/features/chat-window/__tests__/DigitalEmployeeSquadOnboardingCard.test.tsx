import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const mockToastSuccess = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: vi.fn(),
  },
}));

const stableT = (key: string, values?: Record<string, string>) => {
  const translations: Record<string, string> = {
    title: 'Assemble Digital Employee Squad',
    badge: 'Delegate Paradigm',
    description: 'Powered by Delegate orchestration',
    mentionTip: 'Type @ to summon specialized digital employees',
    quickInsertMention: 'Summon Agent',
    assembleSquad: 'Assemble Squad',
    squadReady: `${values?.name || ''} assembled! Ready for orchestrated execution.`,
    'squads.rnd.name': 'Fullstack R&D & Audit Squad',
    'squads.rnd.tagline': 'Architecture · Double Review · QA Loop',
    'squads.rnd.leader': 'Architecture Lead',
    'squads.rnd.workers': 'Strategic Advisor + Code Reviewer + QA Automation',
    'squads.rnd.prompt': 'Assemble the Fullstack R&D Squad to review system architecture and harden automated tests.',
    'squads.research.name': 'Deep Research & Synthesis Squad',
    'squads.research.tagline': 'Multi-source Scout · Cross-check · Deep Report',
    'squads.research.leader': 'Research Director',
    'squads.research.workers': 'Scout Crawler + Fact Checker + Report Synthesizer',
    'squads.research.prompt':
      'Assemble the Deep Research Squad to conduct a comprehensive landscape survey on modern AI agent architectures.',
    'squads.strategy.name': 'Strategic Advisory & Risk Squad',
    'squads.strategy.tagline': 'Read-only Safety · Scenario Modeling · Governance',
    'squads.strategy.leader': 'Strategy Lead',
    'squads.strategy.workers': 'Read-only Strategic Advisor + Security Officer + FinOps Auditor',
    'squads.strategy.prompt':
      'Assemble the Strategic Advisory Squad to assess technical risk boundaries and ROI for our upcoming release.',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockSetInputMessage = vi.fn();
let mockCurrentInput = '';

vi.mock('@/store/useChatStore', () => {
  const store = (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      setInputMessage: mockSetInputMessage,
      inputMessage: mockCurrentInput,
    });
  store.getState = () => ({
    setInputMessage: mockSetInputMessage,
    inputMessage: mockCurrentInput,
  });
  return { default: store };
});

import DigitalEmployeeSquadOnboardingCard from '../DigitalEmployeeSquadOnboardingCard';

describe('DigitalEmployeeSquadOnboardingCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCurrentInput = '';
  });

  it('renders squad orchestration onboarding hub with all 3 preset cards', () => {
    render(<DigitalEmployeeSquadOnboardingCard />);

    expect(screen.getByTestId('digital-employee-squad-onboarding-hub')).toBeInTheDocument();
    expect(screen.getByText('Assemble Digital Employee Squad')).toBeInTheDocument();
    expect(screen.getByText('Delegate Paradigm')).toBeInTheDocument();

    expect(screen.getByTestId('squad-card-rnd')).toBeInTheDocument();
    expect(screen.getByText('Fullstack R&D & Audit Squad')).toBeInTheDocument();

    expect(screen.getByTestId('squad-card-research')).toBeInTheDocument();
    expect(screen.getByText('Deep Research & Synthesis Squad')).toBeInTheDocument();

    expect(screen.getByTestId('squad-card-strategy')).toBeInTheDocument();
    expect(screen.getByText('Strategic Advisory & Risk Squad')).toBeInTheDocument();
  });

  it('assembles squad and prefills starter prompt on click', () => {
    render(<DigitalEmployeeSquadOnboardingCard />);

    const rndCard = screen.getByTestId('squad-card-rnd');
    const assembleBtn = rndCard.querySelector('button');
    expect(assembleBtn).not.toBeNull();

    if (assembleBtn) {
      fireEvent.click(assembleBtn);
    }

    expect(mockSetInputMessage).toHaveBeenCalledWith(
      'Assemble the Fullstack R&D Squad to review system architecture and harden automated tests.',
    );
    expect(mockToastSuccess).toHaveBeenCalledWith(
      'Fullstack R&D & Audit Squad assembled! Ready for orchestrated execution.',
    );
  });

  it('handles quick mention action by prepending or appending @ symbol to input', () => {
    render(<DigitalEmployeeSquadOnboardingCard />);

    const quickMentionBtn = screen.getByTestId('squad-mention-quick-action');
    fireEvent.click(quickMentionBtn);

    expect(mockSetInputMessage).toHaveBeenCalledWith('@');
  });
});
