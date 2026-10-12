/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GroundTruthDriftDefenseCard } from '../command-center/GroundTruthDriftDefenseCard';
import type {
  BatchDriftCheckResponseDTO,
  DriftCheckResponseDTO,
} from '@/services/memory/driftDefense';

const { mockCheckMemoryDrift, mockCheckBatchMemoryDrift } = vi.hoisted(() => ({
  mockCheckMemoryDrift: vi.fn(),
  mockCheckBatchMemoryDrift: vi.fn(),
}));

vi.mock('@/services/memory/driftDefense', () => ({
  checkMemoryDrift: mockCheckMemoryDrift,
  checkBatchMemoryDrift: mockCheckBatchMemoryDrift,
}));

describe('GroundTruthDriftDefenseCard', () => {
  const mockPristineResult: DriftCheckResponseDTO = {
    memory_id: 'mem-drift-probe-01',
    is_drifted: false,
    confidence_penalty: 0.0,
    findings: [],
    decorated_content: 'Use src/services/auth.py AuthService to authenticate user tokens and permissions.',
  };

  const mockDriftedResult: DriftCheckResponseDTO = {
    memory_id: 'mem-stale-01',
    is_drifted: true,
    confidence_penalty: 0.6,
    findings: [
      {
        drift_type: 'file_not_found',
        reference_target: 'src/legacy/obsolete_module.py',
        detail: "Referenced file 'src/legacy/obsolete_module.py' does not exist in active workspace.",
        is_stale: true,
      },
      {
        drift_type: 'symbol_not_found',
        reference_target: 'src/services/auth.py::LegacyCipher',
        detail: "Bound symbol 'LegacyCipher' is no longer found in 'src/services/auth.py'.",
        is_stale: true,
      },
    ],
    decorated_content:
      '[⚠️ 过时警告: 对应业务文件或配置已发生演进，请以当前最新状态为准]\nLegacy validation flow implemented in src/legacy/obsolete_module.py OldValidator.',
  };

  const mockBatchResult: BatchDriftCheckResponseDTO = {
    total_checked: 3,
    drifted_count: 2,
    results: [
      {
        memory_id: 'probe-valid-01',
        is_drifted: false,
        confidence_penalty: 0.0,
        findings: [],
        decorated_content: 'Reference src/services/auth.py AuthService',
      },
      {
        memory_id: 'probe-missing-file-02',
        is_drifted: true,
        confidence_penalty: 0.6,
        findings: [
          {
            drift_type: 'file_not_found',
            reference_target: 'config/deprecated_db.json',
            detail: "Bound file 'config/deprecated_db.json' is missing or deleted from repository.",
            is_stale: true,
          },
        ],
        decorated_content:
          '[⚠️ 过时警告]\nLegacy database settings in config/deprecated_db.json',
      },
      {
        memory_id: 'probe-missing-symbol-03',
        is_drifted: true,
        confidence_penalty: 0.6,
        findings: [
          {
            drift_type: 'symbol_not_found',
            reference_target: 'src/services/auth.py::LegacyCipher',
            detail: "Bound symbol 'LegacyCipher' is no longer found.",
            is_stale: true,
          },
        ],
        decorated_content:
          '[⚠️ 过时警告]\nOld token cipher in src/services/auth.py LegacyCipher',
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial form inputs and accessibility labels', () => {
    render(<GroundTruthDriftDefenseCard />);

    expect(screen.getByText('Ground Truth 真实性漂移防御与过时记忆熔断')).toBeInTheDocument();
    expect(screen.getByLabelText('记忆标识 (Memory ID)')).toBeInTheDocument();
    expect(screen.getByLabelText(/工作区根目录/)).toBeInTheDocument();
    expect(screen.getByLabelText(/绑定物理文件路径/)).toBeInTheDocument();
    expect(screen.getByLabelText(/绑定 AST 类\/函数符号/)).toBeInTheDocument();
    expect(screen.getByLabelText('记忆正文 (Memory Content)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /校验单项真实性/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /执行批量探针沙盒/ })).toBeInTheDocument();
  });

  it('handles single drift check successfully without drift', async () => {
    mockCheckMemoryDrift.mockResolvedValueOnce(mockPristineResult);

    render(<GroundTruthDriftDefenseCard />);

    const checkBtn = screen.getByRole('button', { name: /校验单项真实性/ });
    fireEvent.click(checkBtn);

    await waitFor(() => {
      expect(mockCheckMemoryDrift).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText(/与源码完全一致/)).toBeInTheDocument();
    expect(screen.getByText(/所有引用的物理文件及 AST 符号均在当前工作区真实存在/)).toBeInTheDocument();
  });

  it('handles single drift check with detected drift and penalty', async () => {
    mockCheckMemoryDrift.mockResolvedValueOnce(mockDriftedResult);

    render(<GroundTruthDriftDefenseCard />);

    const checkBtn = screen.getByRole('button', { name: /校验单项真实性/ });
    fireEvent.click(checkBtn);

    await waitFor(() => {
      expect(mockCheckMemoryDrift).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('检测到代码漂移')).toBeInTheDocument();
    expect(screen.getByText('置信度扣减 -60%')).toBeInTheDocument();
    expect(screen.getByText('物理不一致证据 (2 处)')).toBeInTheDocument();
    expect(screen.getByText('物理文件缺失 (file_not_found)')).toBeInTheDocument();
    expect(screen.getByText('函数/类符号缺失 (symbol_not_found)')).toBeInTheDocument();
    expect(screen.getByText(/Prompt-Decorated Preview/)).toBeInTheDocument();
  });

  it('handles batch drift probe sandbox', async () => {
    mockCheckBatchMemoryDrift.mockResolvedValueOnce(mockBatchResult);

    render(<GroundTruthDriftDefenseCard />);

    const batchBtn = screen.getByRole('button', { name: /执行批量探针沙盒/ });
    fireEvent.click(batchBtn);

    await waitFor(() => {
      expect(mockCheckBatchMemoryDrift).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('批量漂移防护沙盒统计')).toBeInTheDocument();
    expect(screen.getByText('评估总量: 3')).toBeInTheDocument();
    expect(screen.getByText('漂移拦截: 2')).toBeInTheDocument();
    expect(screen.getByText('probe-valid-01')).toBeInTheDocument();
    expect(screen.getByText('probe-missing-file-02')).toBeInTheDocument();
  });

  it('loads drift example when button clicked', () => {
    render(<GroundTruthDriftDefenseCard />);

    const exampleBtn = screen.getByRole('button', { name: /载入过时样本/ });
    fireEvent.click(exampleBtn);

    const memIdInput = screen.getByLabelText('记忆标识 (Memory ID)') as HTMLInputElement;
    expect(memIdInput.value).toBe('mem-stale-example');

    const pathInput = screen.getByLabelText(/绑定物理文件路径/) as HTMLInputElement;
    expect(pathInput.value).toBe('src/legacy/obsolete_module.py');
  });
});
