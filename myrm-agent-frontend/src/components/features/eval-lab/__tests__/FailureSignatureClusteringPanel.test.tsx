/**
 * @vitest-environment jsdom
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  FailureSignatureClusteringPanel,
  type SignatureClusterItem,
} from '../components/FailureSignatureClusteringPanel';

// Mock next-intl
const stableT = (key: string, params?: Record<string, unknown>) => {
  const translations: Record<string, string> = {
    panelTitle: 'Failure Signature Clustering & Governance Proposals',
    panelSubtitle: 'Sentry-grade fingerprint normalization & (ci, qi, mi) dual-axis addressability',
    clustersFound: 'clusters found',
    verdictAddressable: 'Addressable (Harness)',
    verdictModelLimit: 'Model-Limit',
    verdictFlake: 'Flake (Transient)',
    cases: 'cases',
    affectedCases: 'Affected Cases',
    sampleQueries: 'Representative Prompts',
    patchProposalTitle: 'Recommended Patch Proposal',
    copyPatch: 'Copy Patch',
    copied: 'Copied',
    reviewAndApply: 'Review & Apply',
  };
  return translations[key] || key;
};
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('FailureSignatureClusteringPanel', () => {
  it('renders nothing when clusters array is empty', () => {
    const { container } = render(<FailureSignatureClusteringPanel clusters={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders signature clusters with verdict badge, case count and patch proposal', () => {
    const mockClusters: SignatureClusterItem[] = [
      {
        cluster_id: 'clust_123',
        ci: 'JSONDecodeError_UnescapedQuotes',
        qi: 'sql_query',
        mi: 'qwen2.5-7b',
        failure_mode: 'tool_argument_malformed',
        verdict: 'addressable',
        case_count: 5,
        affected_case_indices: [0, 2, 4],
        sample_messages: ['SELECT * FROM orders'],
        remediation_hint: 'Enable tool argument repair middleware to handle quotes',
        patch_proposal: {
          op: 'replace',
          path: '/capabilities/tool_repair/enabled',
          value: true,
          rationale: 'Auto-repair unescaped quotes',
          target_component: 'middleware',
        },
      },
      {
        cluster_id: 'clust_456',
        ci: 'Combinatorial_Backtracking_Exhaustion',
        qi: 'math_reasoning',
        mi: 'qwen2.5-7b',
        failure_mode: 'intent_misunderstanding',
        verdict: 'model_limit',
        case_count: 2,
        affected_case_indices: [1, 3],
        sample_messages: ['Prove theorem 4'],
        remediation_hint: 'Model reached reasoning limit, route to DeepSeek-R1',
        patch_proposal: null,
      },
    ];

    render(<FailureSignatureClusteringPanel clusters={mockClusters} profileId="agent_test" />);

    expect(screen.getByText('Failure Signature Clustering & Governance Proposals')).toBeDefined();
    expect(screen.getByText('JSONDecodeError_UnescapedQuotes')).toBeDefined();
    expect(screen.getByText('Addressable (Harness)')).toBeDefined();
    expect(screen.getByText('Model-Limit')).toBeDefined();
    expect(screen.getByText('5 cases')).toBeDefined();
    expect(screen.getByText('2 cases')).toBeDefined();

    // Expand first cluster
    fireEvent.click(screen.getByText('JSONDecodeError_UnescapedQuotes'));
    expect(screen.getByText('Case #1')).toBeDefined();
    expect(screen.getByText('Case #3')).toBeDefined();
    expect(screen.getByText('Case #5')).toBeDefined();
    expect(screen.getByText('SELECT * FROM orders')).toBeDefined();
    expect(screen.getByText('Recommended Patch Proposal (RFC-6902)')).toBeDefined();
    expect(screen.getByText('Review & Apply')).toBeDefined();
  });
});
