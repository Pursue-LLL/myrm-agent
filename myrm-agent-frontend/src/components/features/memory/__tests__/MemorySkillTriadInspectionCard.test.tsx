/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 147 MemorySkillTriadAndScopeIsolationSuite:
 * 1. Default render of skill triad card with header, badges, and scope physical partition.
 * 2. Purges scope partition atomically and displays confirmation notice.
 * 3. Switches to visible degradation observer tab and displays fallback diagnostics.
 * 4. Switches to machine CLI envelope tab and displays JSON envelope with auto-confirmation.
 * 5. Switches to pipeline verification tab and displays 4-question survey & seam validation.
 * 6. Handles API failure gracefully via offline simulation fallback.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MemorySkillTriadInspectionCard } from '../command-center/MemorySkillTriadInspectionCard';
import type {
  ScopePartitionResponse,
  DeleteScopeResponse,
  DegradedReportResponse,
  CliEnvelopeResponse,
  ValidateSurveyResponse,
  VerifySeamsResponse,
} from '@/services/memory/skillTriad';

const {
  mockResolveScope,
  mockDeleteScope,
  mockAssessProviders,
  mockFormatCliEnvelope,
  mockValidateSurvey,
  mockVerifySeams,
  mockGetHealth,
} = vi.hoisted(() => ({
  mockResolveScope: vi.fn(),
  mockDeleteScope: vi.fn(),
  mockAssessProviders: vi.fn(),
  mockFormatCliEnvelope: vi.fn(),
  mockValidateSurvey: vi.fn(),
  mockVerifySeams: vi.fn(),
  mockGetHealth: vi.fn(),
}));

vi.mock('@/services/memory/skillTriad', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    skillTriadApi: {
      resolveScope: mockResolveScope,
      deleteScope: mockDeleteScope,
      assessProviders: mockAssessProviders,
      formatCliEnvelope: mockFormatCliEnvelope,
      validateSurvey: mockValidateSurvey,
      verifySeams: mockVerifySeams,
      getHealth: mockGetHealth.mockResolvedValue({
        status: 'ok',
        module: 'skill_triad',
        version: '1.0.0',
      }),
    },
  };
});

describe('MemorySkillTriadInspectionCard (Item 147 P1)', () => {
  const sampleScopeRes: ScopePartitionResponse = {
    coordinates: {
      tenant_id: 'tenant-enterprise',
      workspace_id: 'ws-prod',
      agent_id: 'analyst-core',
      session_id: 'sess-888',
    },
    namespace_hash: 'e8f7a2b91c0d3e4f5a6b7c8d9e0f1a2b',
    partition_dir: '/var/data/scopes/e8f7a2b91c0d3e4f5a6b7c8d9e0f1a2b',
    sqlite_path: '/var/data/scopes/e8f7a2b91c0d3e4f5a6b7c8d9e0f1a2b/memory.sqlite',
    is_isolated: true,
  };

  const sampleDeleteRes: DeleteScopeResponse = {
    deleted: true,
    namespace_hash: 'e8f7a2b91c0d3e4f5a6b7c8d9e0f1a2b',
  };

  const sampleDegradedRes: DegradedReportResponse = {
    overall_status: 'degraded_lexical_fallback',
    strict_mode: false,
    summary: 'Operating with 1 visibly degraded fallback provider',
    providers: [
      {
        provider_type: 'embedder',
        configured_vendor: 'missing-vendor-x',
        active_vendor: 'builtin_tfidf_128d',
        is_degraded: true,
        degradation_reason:
          "External vendor 'missing-vendor-x' unavailable; degraded visibly to zero-dependency 'builtin_tfidf_128d'.",
      },
      {
        provider_type: 'llm',
        configured_vendor: 'anthropic',
        active_vendor: 'anthropic',
        is_degraded: false,
        degradation_reason: '',
      },
    ],
  };

  const sampleEnvelopeRes: CliEnvelopeResponse = {
    status: 'success',
    command: 'memory.recall',
    duration_ms: 12,
    scope: { tenant_id: 'tenant-enterprise', workspace_id: 'ws-prod' },
    payload: { query: 'financial report', recalled_items: '3' },
    error_code: '',
    error_message: '',
    exit_code: 0,
    auto_confirmed: true,
  };

  const sampleSurveyRes: ValidateSurveyResponse = {
    is_valid: true,
    issues: [],
  };

  const sampleSeamRes: VerifySeamsResponse = {
    is_verified: true,
    message: 'All integration seams and pre-flight round-trip tests successfully verified.',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockResolveScope.mockResolvedValue(sampleScopeRes);
    mockDeleteScope.mockResolvedValue(sampleDeleteRes);
    mockAssessProviders.mockResolvedValue(sampleDegradedRes);
    mockFormatCliEnvelope.mockResolvedValue(sampleEnvelopeRes);
    mockValidateSurvey.mockResolvedValue(sampleSurveyRes);
    mockVerifySeams.mockResolvedValue(sampleSeamRes);
  });

  it('1. renders header, core badges, and scope partition data by default', async () => {
    render(<MemorySkillTriadInspectionCard />);

    expect(screen.getByText('Memory Skill Triad & Scope Isolation Suite')).toBeInTheDocument();
    expect(screen.getByText('Item 147 · Mnemosyne 8.0.0')).toBeInTheDocument();
    expect(screen.getByText('Zero-Dependency Core')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockResolveScope).toHaveBeenCalled();
    });

    expect(await screen.findByText(/SHA256\[:32\]: e8f7a2b91c0d3e4f5a6b7c8d9e0f1a2b/)).toBeInTheDocument();
    expect(screen.getByText(/独立 SQLite: \/var\/data\/scopes\/e8f7a2b91c0d3e4f5a6b7c8d9e0f1a2b\/memory\.sqlite/)).toBeInTheDocument();
  });

  it('2. triggers atomic scope deletion and displays confirmation feedback', async () => {
    render(<MemorySkillTriadInspectionCard />);

    await waitFor(() => {
      expect(mockResolveScope).toHaveBeenCalled();
    });

    const deleteBtn = await screen.findByRole('button', { name: /物理原子清理/ });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(mockDeleteScope).toHaveBeenCalledWith({ coordinates: sampleScopeRes.coordinates });
    });

    expect(await screen.findByText(/Scope partition e8f7a2b9\.\.\. purged atomically\./)).toBeInTheDocument();
  });

  it('3. switches to visible degradation observer tab and renders fallback reports', async () => {
    render(<MemorySkillTriadInspectionCard />);

    const degradedTabBtn = screen.getByRole('button', { name: /可见降级观测/ });
    fireEvent.click(degradedTabBtn);

    await waitFor(() => {
      expect(mockAssessProviders).toHaveBeenCalled();
    });

    expect(await screen.findByText('degraded_lexical_fallback')).toBeInTheDocument();
    expect(screen.getByText(/已降级: builtin_tfidf_128d/)).toBeInTheDocument();
    expect(screen.getByText(/正常在线: anthropic/)).toBeInTheDocument();
  });

  it('4. switches to machine CLI envelope tab and displays JSON with auto-confirmation', async () => {
    render(<MemorySkillTriadInspectionCard />);

    const cliTabBtn = screen.getByRole('button', { name: /机器 CLI 信封/ });
    fireEvent.click(cliTabBtn);

    await waitFor(() => {
      expect(mockFormatCliEnvelope).toHaveBeenCalled();
    });

    expect(await screen.findByText(/auto_confirmed: true/)).toBeInTheDocument();
    expect(screen.getByText(/"command": "memory.recall"/)).toBeInTheDocument();
  });

  it('5. switches to pipeline verification tab and displays 4-question survey & seam validation', async () => {
    render(<MemorySkillTriadInspectionCard />);

    const pipelineTabBtn = screen.getByRole('button', { name: /集成流水线校验/ });
    fireEvent.click(pipelineTabBtn);

    await waitFor(() => {
      expect(mockValidateSurvey).toHaveBeenCalled();
      expect(mockVerifySeams).toHaveBeenCalled();
    });

    expect(await screen.findByText(/代码库 4 问调查评估完整/)).toBeInTheDocument();
    expect(screen.getByText(/All integration seams and pre-flight round-trip tests successfully verified\./)).toBeInTheDocument();
  });

  it('6. handles API errors gracefully with offline simulation fallback', async () => {
    mockResolveScope.mockRejectedValueOnce(new Error('Network error'));
    render(<MemorySkillTriadInspectionCard />);

    // Should fall back to mock offline partition without crashing
    expect(await screen.findByText(/SHA256\[:32\]: e8f7a2b91c0d3e4f5a6b7c8d9e0f1a2b/)).toBeInTheDocument();
  });
});
