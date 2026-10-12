/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/ruleCascade::queryCascadedRules, listAllDeterministicRules, preFilterEvidence
 * ../command-center/DeterministicRuleCascadeCard::DeterministicRuleCascadeCard
 *
 * [OUTPUT]
 * Test suite verifying Claude Code deterministic rule cascade, leaf override resolution,
 * and physical 5-dimensional metadata pre-filtering telemetry.
 *
 * [POS]
 * Unit test for Item 99 (FiveDimPreFilteredEvidenceMemoryAndDeterministicRuleCascadeSuite).
 * Strict typing applied: No `any` types allowed. File lines < 350.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DeterministicRuleCascadeCard } from '../command-center/DeterministicRuleCascadeCard';
import type {
  CascadedRuleSetDTO,
  DeterministicRuleEntryDTO,
  PreFilteredEvidenceResponseDTO,
} from '@/services/memory/ruleCascade';

const {
  mockQueryCascadedRules,
  mockListAllDeterministicRules,
  mockPreFilterEvidence,
} = vi.hoisted(() => ({
  mockQueryCascadedRules: vi.fn(),
  mockListAllDeterministicRules: vi.fn(),
  mockPreFilterEvidence: vi.fn(),
}));

vi.mock('@/services/memory/ruleCascade', () => ({
  queryCascadedRules: mockQueryCascadedRules,
  listAllDeterministicRules: mockListAllDeterministicRules,
  preFilterEvidence: mockPreFilterEvidence,
}));

describe('DeterministicRuleCascadeCard', () => {
  const sampleRules: DeterministicRuleEntryDTO[] = [
    {
      rule_id: 'rule-root-pep8',
      title: 'Code Formatting & Style',
      rule_content: 'Standard PEP-8 line length 100 with strict black formatter.',
      metadata: {
        scope: 'global',
        scope_path: '/',
        source: 'user_explicit',
        source_authority: 1.0,
        created_at: '2026-10-08T04:00:00Z',
        half_life_days: 30.0,
        confidence: 1.0,
        permission: 'public',
      },
      is_enforced: true,
    },
    {
      rule_id: 'rule-ws-test',
      title: 'Testing Standard',
      rule_content: 'Mandatory pytest with 90% coverage and zero mock leaking.',
      metadata: {
        scope: 'workspace',
        scope_path: '/workspace',
        source: 'tool_verified',
        source_authority: 0.8,
        created_at: '2026-10-08T04:00:00Z',
        half_life_days: 30.0,
        confidence: 1.0,
        permission: 'workspace_internal',
      },
      is_enforced: true,
    },
    {
      rule_id: 'rule-billing-strict',
      title: 'Code Formatting & Style',
      rule_content: 'Strict zero-warning Ruff & mypy checks required before PR.',
      metadata: {
        scope: 'directory',
        scope_path: '/workspace/packages/billing',
        source: 'user_explicit',
        source_authority: 1.0,
        created_at: '2026-10-08T04:00:00Z',
        half_life_days: 30.0,
        confidence: 1.0,
        permission: 'workspace_internal',
      },
      is_enforced: true,
    },
  ];

  const sampleCascaded: CascadedRuleSetDTO = {
    target_path: '/workspace/packages/billing/controllers',
    inherited_rules: [sampleRules[1], sampleRules[2]],
    effective_rules_count: 2,
    sources_breakdown: {
      user_explicit: 1,
      tool_verified: 1,
    },
  };

  const sampleAuditResponse: PreFilteredEvidenceResponseDTO = {
    passed_items: [sampleRules[1]],
    total_evaluated: 3,
    passed_count: 1,
    rejection_reasons: {
      permission_denied: 1,
      authority_insufficient: 1,
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockQueryCascadedRules.mockResolvedValue(sampleCascaded);
    mockListAllDeterministicRules.mockResolvedValue(sampleRules);
    mockPreFilterEvidence.mockResolvedValue(sampleAuditResponse);
  });

  it('renders card title, subtitle, and HUD 4-dimensional metrics', async () => {
    render(<DeterministicRuleCascadeCard />);

    expect(screen.getByText('Deterministic Rule Cascade & 5D Pre-Filter Suite')).toBeInTheDocument();
    expect(screen.getByText(/Item 99 • Claude Code Cascade/i)).toBeInTheDocument();
    expect(screen.getByText('Pre-Filter Isolation')).toBeInTheDocument();
    expect(screen.getByText('Half-life Decay')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Testing Standard')).toBeInTheDocument();
      expect(screen.getByText('Strict zero-warning Ruff & mypy checks required before PR.')).toBeInTheDocument();
    });
  });

  it('allows querying and resolving cascade for a new directory path', async () => {
    render(<DeterministicRuleCascadeCard />);

    await waitFor(() => {
      expect(screen.getByText('Testing Standard')).toBeInTheDocument();
    });

    const pathInput = screen.getByPlaceholderText('/workspace/packages/billing/controllers');
    const form = screen.getByRole('form', { name: 'query-path-form' });

    fireEvent.change(pathInput, { target: { value: '/workspace/packages/auth' } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockQueryCascadedRules).toHaveBeenCalledWith('/workspace/packages/auth');
    });
  });

  it('switches to 5D Physical Pre-Filter Audit tab and renders filter parameters', async () => {
    render(<DeterministicRuleCascadeCard />);

    const auditTabBtn = screen.getByRole('button', { name: /5D Physical Pre-Filter Audit/i });
    fireEvent.click(auditTabBtn);

    await waitFor(() => {
      expect(screen.getByText('Physical 5-Dimensional Pre-Filter Guard')).toBeInTheDocument();
      expect(screen.getByLabelText(/Dim 1: Scope Path Prefix/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Execute Pre-Filter Audit/i })).toBeInTheDocument();
    });
  });

  it('executes pre-filter boundary audit and displays rejection breakdown and safe items', async () => {
    render(<DeterministicRuleCascadeCard />);

    const auditTabBtn = screen.getByRole('button', { name: /5D Physical Pre-Filter Audit/i });
    fireEvent.click(auditTabBtn);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Execute Pre-Filter Audit/i })).toBeInTheDocument();
    });

    const auditForm = screen.getByRole('form', { name: 'pre-filter-audit-form' });
    fireEvent.submit(auditForm);

    await waitFor(() => {
      expect(mockPreFilterEvidence).toHaveBeenCalledWith(
        expect.objectContaining({
          candidates: sampleRules,
          scope_path_prefix: '/workspace',
          min_authority: 0.8,
        })
      );
      expect(screen.getByText('Pre-Filter Rejection Breakdown (Physical Isolation Gate)')).toBeInTheDocument();
      expect(screen.getByText('permission_denied: 1')).toBeInTheDocument();
      expect(screen.getByText('authority_insufficient: 1')).toBeInTheDocument();
      expect(screen.getByText('Safe Candidate Memories Permitted for Prompt Context')).toBeInTheDocument();
    });
  });

  it('falls back gracefully to offline mock defaults if service rejects', async () => {
    mockQueryCascadedRules.mockRejectedValue(new Error('Network failure'));
    mockListAllDeterministicRules.mockRejectedValue(new Error('Network failure'));

    render(<DeterministicRuleCascadeCard />);

    await waitFor(() => {
      expect(screen.getByText('Testing Standard')).toBeInTheDocument();
      expect(screen.getByText('Mandatory pytest with 90% coverage and zero mock leaking.')).toBeInTheDocument();
    });
  });
});
