import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// Mock next-intl
const deliverableTranslations: Record<string, string> = {
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

const stableT = (key: string) => deliverableTranslations[key] || key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/primitives/hover-card', () => ({
  HoverCard: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  HoverCardTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  HoverCardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { DeliverableTierBadge } from '../DeliverableTierBadge';

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
    expect(screen.getAllByText('Verified Delivery').length).toBeGreaterThanOrEqual(1);
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
    expect(screen.getAllByText('Artifact Delivery').length).toBeGreaterThanOrEqual(1);
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
    expect(screen.getAllByText('Research Output').length).toBeGreaterThanOrEqual(1);
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
    expect(screen.getAllByText('Plan / Proposal').length).toBeGreaterThanOrEqual(1);
  });
});
