/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory::(fetchVectorSpaceStatus, validateVectorSpace, bindVectorSpace, reindexVectorSpace)
 * ../command-center/VectorSpaceGuardStudioCard::VectorSpaceGuardStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Item 131 EmbeddingModelDimensionAndVectorSpaceGuardSuite:
 * 1. Default render of HUD status bar, collection input, and model fingerprints
 * 2. Pre-flight compatibility validation with consistent outcome
 * 3. Pre-flight validation flagging dimension mismatch and recommending reindex
 * 4. Executing safe vector space migration and reindexing pipeline
 * 5. Resilient fallback and alert banner on network or API errors
 *
 * [POS]
 * Unit tests for Item 131.
 * Strict typing applied: Zero `any` types. Single file < 200 lines.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { VectorSpaceGuardStudioCard } from '../command-center/VectorSpaceGuardStudioCard';
import {
  FALLBACK_REINDEX_RESPONSE,
  FALLBACK_SPACE_STATUS,
  FALLBACK_VALIDATE_RESPONSE,
} from '../command-center/vectorSpaceGuardFallbacks';

const {
  mockFetchStatus,
  mockValidateSpace,
  mockBindSpace,
  mockReindexSpace,
} = vi.hoisted(() => ({
  mockFetchStatus: vi.fn(),
  mockValidateSpace: vi.fn(),
  mockBindSpace: vi.fn(),
  mockReindexSpace: vi.fn(),
}));

vi.mock('@/services/memory', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    fetchVectorSpaceStatus: mockFetchStatus,
    validateVectorSpace: mockValidateSpace,
    bindVectorSpace: mockBindSpace,
    reindexVectorSpace: mockReindexSpace,
  };
});

describe('VectorSpaceGuardStudioCard (Item 131 P0)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchStatus.mockResolvedValue(FALLBACK_SPACE_STATUS);
    mockValidateSpace.mockResolvedValue(FALLBACK_VALIDATE_RESPONSE);
    mockBindSpace.mockResolvedValue({
      collection: 'working_memory',
      fingerprint: FALLBACK_SPACE_STATUS.fingerprint,
      status: 'bound',
    });
    mockReindexSpace.mockResolvedValue(FALLBACK_REINDEX_RESPONSE);
  });

  it('renders default HUD status bar, collection input, and model fingerprints', async () => {
    render(<VectorSpaceGuardStudioCard />);

    expect(screen.getByText('向量空间与模型维度守卫')).toBeInTheDocument();
    expect(screen.getByText('目标集合：')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('已受保护')).toBeInTheDocument();
      expect(screen.getByText('openai/text-embedding-3-small')).toBeInTheDocument();
      expect(screen.getByText('1536d (cosine)')).toBeInTheDocument();
      expect(screen.getByText('128')).toBeInTheDocument();
    });

    expect(
      screen.getByText('运行时模型指纹与预检校验')
    ).toBeInTheDocument();
    expect(
      screen.getByText('空间迁移与向量重索引流水线')
    ).toBeInTheDocument();
  });

  it('triggers pre-flight compatibility validation with consistent outcome', async () => {
    render(<VectorSpaceGuardStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('已受保护')).toBeInTheDocument();
    });

    const validateBtn = screen.getByRole('button', { name: /执行预检校验/i });
    fireEvent.click(validateBtn);

    await waitFor(() => {
      expect(mockValidateSpace).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(screen.getByText(/通过 \(Consistent\)/i)).toBeInTheDocument();
      expect(
        screen.getByText('运行时模型与集合向量空间完全一致')
      ).toBeInTheDocument();
      expect(screen.getByText('proceed')).toBeInTheDocument();
    });
  });

  it('handles dimension mismatch and surfaces recommended reindex action', async () => {
    mockValidateSpace.mockResolvedValueOnce({
      is_valid: false,
      status: 'dimension_mismatch',
      message: '维度失配：集合注册维度 1536d，运行时维度 3072d',
      recommended_action: 'reindex_required',
      expected_fingerprint: FALLBACK_SPACE_STATUS.fingerprint,
      current_fingerprint: {
        provider_id: 'openai',
        model_name: 'text-embedding-3-large',
        vector_dimension: 3072,
        metric_type: 'cosine',
      },
    });

    render(<VectorSpaceGuardStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('已受保护')).toBeInTheDocument();
    });

    const validateBtn = screen.getByRole('button', { name: /执行预检校验/i });
    fireEvent.click(validateBtn);

    await waitFor(() => {
      expect(screen.getByText(/异常 \(dimension_mismatch\)/i)).toBeInTheDocument();
      expect(
        screen.getByText('维度失配：集合注册维度 1536d，运行时维度 3072d')
      ).toBeInTheDocument();
      expect(screen.getByText('reindex_required')).toBeInTheDocument();
    });
  });

  it('triggers safe space migration and reindexing pipeline successfully', async () => {
    render(<VectorSpaceGuardStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('已受保护')).toBeInTheDocument();
    });

    const reindexBtn = screen.getByRole('button', { name: /启动安全空间迁移/i });
    fireEvent.click(reindexBtn);

    await waitFor(() => {
      expect(mockReindexSpace).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(screen.getByText('已完成')).toBeInTheDocument();
      expect(screen.getByText('重新嵌入向量数:')).toBeInTheDocument();
      expect(
        screen.getByText('集合向量空间与新基底模型指纹已成功同步！')
      ).toBeInTheDocument();
    });
  });

  it('renders fallback alert banner when status fetch encounters network failure', async () => {
    mockFetchStatus.mockRejectedValueOnce(new Error('Network error'));

    render(<VectorSpaceGuardStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByText('无法连接向量空间守卫服务，已载入离线降级状态')
      ).toBeInTheDocument();
    });
  });
});
