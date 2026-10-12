/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CodeMemoryCompactionCard } from '../command-center/CodeMemoryCompactionCard';

const { mockCompactCodeMemory, mockExtractCodeSkeleton } = vi.hoisted(() => ({
  mockCompactCodeMemory: vi.fn(),
  mockExtractCodeSkeleton: vi.fn(),
}));

vi.mock('@/services/memory/codeCompaction', () => ({
  compactCodeMemory: mockCompactCodeMemory,
  extractCodeSkeleton: mockExtractCodeSkeleton,
}));

describe('CodeMemoryCompactionCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial form fields and actions correctly', () => {
    render(<CodeMemoryCompactionCard />);

    expect(screen.getByText('代码语义记忆骨架化压缩引擎')).toBeInTheDocument();
    expect(screen.getByText('Token 预算感知')).toBeInTheDocument();
    expect(screen.getByLabelText(/文件路径/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Token 预算上限/)).toBeInTheDocument();
    expect(screen.getByLabelText(/待压缩代码内容/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /提取骨架/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /预算压缩/ })).toBeInTheDocument();
  });

  it('extracts skeleton successfully and displays compacted block', async () => {
    mockExtractCodeSkeleton.mockResolvedValueOnce({
      abstraction_level: 'L1_SIGNATURES',
      content: 'def process_node(self, node: dict) -> bool: ...',
      original_token_count: 85,
      compacted_token_count: 20,
    });

    render(<CodeMemoryCompactionCard />);

    const extractBtn = screen.getByRole('button', { name: /提取骨架/ });
    fireEvent.click(extractBtn);

    await waitFor(() => {
      expect(mockExtractCodeSkeleton).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('L1 结构签名')).toBeInTheDocument();
    expect(screen.getByText('def process_node(self, node: dict) -> bool: ...')).toBeInTheDocument();
    expect(screen.getByText('85')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
  });

  it('runs budget compaction and updates token reduction ratio', async () => {
    mockCompactCodeMemory.mockResolvedValueOnce({
      compacted_blocks: [
        {
          file_path: 'src/engine/compactor.py',
          abstraction_level: 'L2_CONTROL_FLOW',
          content: 'def process_node(self, node: dict):\n    if not node: return False\n    return True',
          original_token_count: 100,
          compacted_token_count: 35,
        },
      ],
      total_original_tokens: 100,
      total_compacted_tokens: 35,
      budget_limit: 120,
      compression_ratio: 0.65,
    });

    render(<CodeMemoryCompactionCard />);

    const compactBtn = screen.getByRole('button', { name: /预算压缩/ });
    fireEvent.click(compactBtn);

    await waitFor(() => {
      expect(mockCompactCodeMemory).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('L2 控制流骨架')).toBeInTheDocument();
    expect(screen.getByText('35 / 100 Tokens')).toBeInTheDocument();
    expect(screen.getByText(/已根据 Token 预算 120 完成动态压缩/)).toBeInTheDocument();
  });

  it('displays error message when API call fails', async () => {
    mockExtractCodeSkeleton.mockRejectedValueOnce(new Error('Syntax parser failure'));

    render(<CodeMemoryCompactionCard />);

    const extractBtn = screen.getByRole('button', { name: /提取骨架/ });
    fireEvent.click(extractBtn);

    expect(await screen.findByText(/错误: Syntax parser failure/)).toBeInTheDocument();
  });
});
