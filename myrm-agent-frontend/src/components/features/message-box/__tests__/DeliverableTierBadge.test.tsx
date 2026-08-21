import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { DeliverableTierBadge } from '../DeliverableTierBadge';

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const map: Record<string, string> = {
      verified: 'Verified Delivery',
      verifiedDesc: 'Passed automated tests or checks',
      artifact: 'Artifact Delivery',
      artifactDesc: 'Generated workspace files',
      research: 'Research Output',
      researchDesc: 'Backed by external research',
      plan: 'Plan / Proposal',
      planDesc: 'Conceptual proposal',
      evidenceDetails: 'Evidence Details',
      verificationsPassed: 'Verifications Passed',
      artifactsWritten: 'Artifacts Written',
      sourcesConsulted: 'Sources Consulted',
    };
    return map[key] || key;
  },
}));

describe('DeliverableTierBadge', () => {
  it('renders verified tier badge correctly', () => {
    render(
      <DeliverableTierBadge
        data={{
          tier: 'VERIFIED',
          evidence: {
            verification_count: 2,
            verification_categories: ['pytest'],
            files_written: ['src/main.py'],
            sources_count: 1,
            gatekeeper_passed: true,
            details: '2 verifications passed',
          },
        }}
      />,
    );

    expect(screen.getByTestId('deliverable-tier-badge-verified')).toBeInTheDocument();
    expect(screen.getByText('Verified Delivery')).toBeInTheDocument();
  });

  it('renders artifact tier badge correctly', () => {
    render(
      <DeliverableTierBadge
        data={{
          tier: 'ARTIFACT',
          evidence: {
            verification_count: 0,
            verification_categories: [],
            files_written: ['README.md'],
            sources_count: 0,
            gatekeeper_passed: false,
            details: '1 artifacts written',
          },
        }}
      />,
    );

    expect(screen.getByTestId('deliverable-tier-badge-artifact')).toBeInTheDocument();
    expect(screen.getByText('Artifact Delivery')).toBeInTheDocument();
  });

  it('renders research tier badge correctly', () => {
    render(
      <DeliverableTierBadge
        data={{
          tier: 'RESEARCH',
          evidence: {
            verification_count: 0,
            verification_categories: [],
            files_written: [],
            sources_count: 3,
            gatekeeper_passed: false,
            details: '3 research sources consulted',
          },
        }}
      />,
    );

    expect(screen.getByTestId('deliverable-tier-badge-research')).toBeInTheDocument();
    expect(screen.getByText('Research Output')).toBeInTheDocument();
  });

  it('renders plan tier badge correctly', () => {
    render(
      <DeliverableTierBadge
        data={{
          tier: 'PLAN',
          evidence: {
            verification_count: 0,
            verification_categories: [],
            files_written: [],
            sources_count: 0,
            gatekeeper_passed: false,
            details: 'Plan/Discussion',
          },
        }}
      />,
    );

    expect(screen.getByTestId('deliverable-tier-badge-plan')).toBeInTheDocument();
    expect(screen.getByText('Plan / Proposal')).toBeInTheDocument();
  });
});
